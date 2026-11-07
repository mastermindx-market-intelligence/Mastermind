"""Fixed, read-only remote half of the incumbent Fabric artifact export."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys

MAX_FILE = 262144
MAX_TOTAL = 1048576
MAX_FILES = 8
MAX_REQUEST = 16384
MAX_RESPONSE = 1500000
SCHEMA = "mastermind.fabric_artifact_read.v1"
COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")

# Separate source-admitted CURRENT intent. No historical packet/lease seal is
# inferred. Changing this scope requires its own exact-source review/admission.
CAPSULE_DIAG_SCHEMA = 'mastermind.fabric_capsule_directory_diagnosis.v1'
CAPSULE_SCHEMA = 'mastermind.fabric_capsule_current_read.v1'
CAPSULE_INTENT = {'allowed_names': ['intlInvestigationComposition.ts',
                   'contract_repair.test.mts',
                   'panel_contract_repair.test.tsx',
                   'FIELD_ORIGINS_R2.md',
                   'RETURN.md'],
 'cwd': '~/lanes/artifacts/paper-waves-01a1101f/im08-im09-contract-repair-r2',
 'declaration_sha256': '1a01c365cba51e636c764af148e02d7ee0da4a356b546c3a5f7d1d26247353ce',
 'host': 'ubuntu0',
 'parent': '01a1101f-2a37-7320-9a9b-5df3ce1b890d',
 'root': '01a1101f-2a37-7320-9a9b-5df3ce1b890d',
 'run_id': 'paper-01a1101f-im08-im09-contract-repair-r2',
 'stdout_sha256': 'a8800c6883b74faaa78accb475c83d0abdabdb617549d65768276f4be52764ba'}


BRIDGE_INTENT = {'allowed_names': ['BRIDGE_RETURN.json'],
 'cwd': '~',
 'declaration_sha256': 'b0f5fd0acdfdaac533a897c9c704a695d6dd26b07185eeae712ecafd05580b2c',
 'expected_sizes': {'BRIDGE_RETURN.json': 66650},
 'host': 'ubuntu0',
 'parent': '01a11057-3134-76d2-bcd1-784d69cc17d3',
 'root': '01a1101f-2a37-7320-9a9b-5df3ce1b890d',
 'run_id': 'paper-01a1101f-intl-owner-bridge-build-r1',
 'stdout_sha256': '7d9ec40d6dfbc2dc29fd3e99ba27e737ce9166ef650f8945bf9c74ffedf59070'}


def capsule_request(run_id):
    if run_id == BRIDGE_INTENT["run_id"]:
        return {**{k:BRIDGE_INTENT[k] for k in ("run_id","root","parent","host","cwd","stdout_sha256","declaration_sha256")},
                "schema":CAPSULE_SCHEMA,"names":list(BRIDGE_INTENT["allowed_names"]),
                "expected_sizes":dict(BRIDGE_INTENT["expected_sizes"])}
    if run_id != CAPSULE_INTENT.get('run_id'):
        raise ValueError('capsule_current_intent_not_admitted')
    result = {key:CAPSULE_INTENT[key] for key in
              ('run_id','root','parent','host','cwd','stdout_sha256','declaration_sha256')}
    return dict(result,schema=CAPSULE_SCHEMA,names=list(CAPSULE_INTENT['allowed_names']))


def validate_capsule_request(request):
    expected = capsule_request(request.get('run_id') if type(request) is dict else None)
    if type(request) is not dict or request != expected:
        raise ValueError('capsule_current_intent_mismatch')
    parts = request['cwd'].split('/')
    if request['run_id'] != BRIDGE_INTENT['run_id'] and (len(parts)!=5 or parts[:3]!=['~','lanes','artifacts']
            or any(not COMPONENT.fullmatch(p) or p in ('.','..') for p in parts[3:])):
        raise ValueError('capsule_cwd_invalid')
    names = request['names']
    if (type(names) is not list or not 1<=len(names)<=MAX_FILES or len(set(names))!=len(names)
            or any(type(n) is not str or not COMPONENT.fullmatch(n)
                   or n in ('.','..','request.json','receipt.json') for n in names)):
        raise ValueError('capsule_output_name_invalid')


def capsule_paths(request):
    return [request['cwd']+'/'+name for name in request['names']]


def read_capsule_one(request, name, remaining):
    path = request['cwd']+'/'+name
    fds, edges = [], []
    try:
        validate_capsule_request(request)
        if name not in request['names']:
            raise ValueError('capsule_output_name_invalid')
        # Unix account home is supplied by the authenticated host, never by a
        # request, HOME override, shell expansion, or arbitrary remote path.
        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        if not home.is_absolute() or '..' in home.parts:
            raise ValueError('directory_owner_or_mode')
        fds.append(os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW))
        components = [*home.parts[1:],*request['cwd'].split('/')[1:]]
        for component in components:
            fd = os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fds[-1])
            info = os.fstat(fd)
            fds.append(fd);edges.append((component,info))
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0,os.getuid())
                    or info.st_mode & 0o022):
                raise ValueError('directory_owner_or_mode')
        fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fds[-1])
        fds.append(fd)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
                or before.st_mode & 0o002 or before.st_nlink!=1):
            raise ValueError('file_owner_mode_or_type')
        if 'expected_sizes' in request and before.st_size != request['expected_sizes'][name]:
            raise ValueError('declared_size_mismatch')
        if before.st_size>min(MAX_FILE,remaining):
            raise ValueError('size_limit')
        budget = min(MAX_FILE,remaining)+1
        chunks=[]
        while budget:
            chunk=os.read(fd,min(65536,budget))
            if not chunk:break
            chunks.append(chunk);budget-=len(chunk)
        raw=b''.join(chunks)
        if (identity(before)!=identity(os.fstat(fd)) or len(raw)!=before.st_size
                or identity(before)!=identity(os.stat(name,dir_fd=fds[-2],follow_symlinks=False))):
            raise ValueError('changed_during_read')
        for index,(component,info) in enumerate(edges):
            if (identity(info)!=identity(os.fstat(fds[index+1]))
                    or identity(info)!=identity(os.stat(component,dir_fd=fds[index],follow_symlinks=False))):
                raise ValueError('changed_during_read')
        return {'path':path,'status':'RETRIEVED','bytes':len(raw),
                'sha256':hashlib.sha256(raw).hexdigest(),'data_base64':base64.b64encode(raw).decode(),
                'observed_file':{'device':before.st_dev,'inode':before.st_ino,'mtime_ns':before.st_mtime_ns,
                                 'uid':before.st_uid,'mode':stat.S_IMODE(before.st_mode)}}
    except FileNotFoundError:
        return {'path':path,'status':'NOT_FOUND','reason':'missing_at_read'}
    except (OSError,ValueError) as exc:
        return {'path':path,'status':'UNAVAILABLE',
                'reason':str(exc) if isinstance(exc,ValueError) else 'filesystem_refused'}
    finally:
        for fd in reversed(fds):os.close(fd)


def collect_capsule(request):
    validate_capsule_request(request)
    files=[];remaining=MAX_TOTAL
    for name in request['names']:
        item=read_capsule_one(request,name,remaining)
        remaining-=item.get('bytes',0);files.append(item)
    return {'schema':CAPSULE_SCHEMA,'request_sha256':hashlib.sha256(canonical(request)).hexdigest(),'files':files}


def _fail(index, role, reason, info=None, errno=None):
    if info is None:
        return {'component_index': index, 'role': role, 'reason': reason,
                'owner_relation': None, 'mode': None, 'errno': errno}
    return {'component_index': index, 'role': role, 'reason': reason,
            'owner_relation': _owner(info.st_uid, os.getuid()),
            'mode': format(stat.S_IMODE(info.st_mode), '04o'), 'errno': errno}


def _diag(status, checked, failure):
    return {'operation': 'capsule_directory_diagnosis', 'status': status,
            'checked_components': checked, 'failure': failure,
            'artifact_files_opened': 0, 'artifact_bytes_read': 0}


def _role(index, home_depth):
    if index < home_depth:
        return 'home_ancestor'
    return ('lanes', 'artifacts', 'project', 'run', 'work')[index - home_depth]


def _owner(uid, current_uid):
    if uid == 0:
        return 'root'
    return 'current' if uid == current_uid else 'other'


def _safe_errno(exc):
    value = getattr(exc, 'errno', None)
    return value if type(value) is int and 0 < value <= 0xffff else None


def diagnose_capsule_directories(request):
    """Metadata-only capsule directory-chain diagnosis (inert, read-free):
    replays the read_capsule_one directory walk, reports the first failing
    ownership/mode predicate, opens no artifact file, reads no bytes. SAFE
    is diagnostic only, never permission."""
    fds, edges = [], []
    try:
        try:
            validate_capsule_request(request)
        except (ValueError, TypeError):
            return _diag('UNAVAILABLE', 0, _fail(None, 'request', 'invalid_request'))
        try:
            home_dir = pwd.getpwuid(os.getuid()).pw_dir
        except OSError as exc:
            return _diag('UNAVAILABLE', 0,
                         _fail(None, 'home', 'filesystem_refused', errno=_safe_errno(exc)))
        except KeyError:
            home_dir = None
        home = Path(home_dir) if type(home_dir) is str else None
        if home is None or not home.is_absolute() or '..' in home.parts:
            return _diag('UNAVAILABLE', 0,
                         _fail(None, 'home_ancestor', 'home_shape_invalid'))
        components = [*home.parts[1:], *request['cwd'].split('/')[1:]]
        home_depth = len(home.parts) - 1
        try:
            fds.append(os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        except OSError as exc:
            return _diag('UNAVAILABLE', 0,
                         _fail(None, 'root', 'filesystem_refused', errno=_safe_errno(exc)))
        checked = 0
        for index, component in enumerate(components):
            role = _role(index, home_depth)
            try:
                fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fds[-1])
                fds.append(fd)
                info = os.fstat(fd)
            except OSError as exc:
                return _diag('UNAVAILABLE', checked,
                             _fail(index, role, 'filesystem_refused', errno=_safe_errno(exc)))
            checked += 1
            edges.append((component, info))
            if not stat.S_ISDIR(info.st_mode):
                return _diag('UNSAFE_CHAIN', checked, _fail(index, role, 'not_directory', info))
            if info.st_uid not in (0, os.getuid()):
                return _diag('UNSAFE_CHAIN', checked, _fail(index, role, 'foreign_owner', info))
            if info.st_mode & 0o022:
                return _diag('UNSAFE_CHAIN', checked, _fail(index, role, 'group_or_world_writable', info))
        for index, (component, info) in enumerate(edges):
            role = _role(index, home_depth)
            try:
                stable = (identity(info) == identity(os.fstat(fds[index + 1]))
                          and identity(info) == identity(os.stat(
                              component, dir_fd=fds[index], follow_symlinks=False)))
            except OSError as exc:
                return _diag('UNAVAILABLE', checked,
                             _fail(index, role, 'filesystem_refused', errno=_safe_errno(exc)))
            if not stable:
                return _diag('UNAVAILABLE', checked, _fail(index, role, 'changed_during_diagnosis', info))
        return _diag('SAFE_CHAIN', checked, None)
    finally:
        close_failure = None
        for position in reversed(range(len(fds))):
            try:
                os.close(fds[position])
            except OSError as exc:
                if close_failure is None:
                    index = position - 1 if position else None
                    role = _role(index, home_depth) if position else 'root'
                    close_failure = _fail(index, role, 'filesystem_refused', errno=_safe_errno(exc))
        if close_failure is not None:
            return _diag('UNAVAILABLE', checked, close_failure)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def validate_path(path):
    # This initial capability is deliberately limited to detached /tmp/DIR/FILE.
    # No home, hidden credential paths, recursive collection or shell expansion.
    if not isinstance(path, str) or len(path) > 270:
        raise ValueError("path_invalid")
    parts = path.split("/")
    if len(parts) != 4 or parts[:2] != ["", "tmp"] or any(
        not COMPONENT.fullmatch(part) or part in {".", ".."} for part in parts[2:]
    ):
        raise ValueError("path_invalid")
    return parts[2:]


def validate_request(request):
    keys = {"schema", "run_id", "root", "parent", "host", "stdout_sha256", "paths"}
    if not isinstance(request, dict) or set(request) != keys or request["schema"] != SCHEMA:
        raise ValueError("request_invalid")
    for key in ("run_id", "root", "parent", "host"):
        if not isinstance(request[key], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", request[key]):
            raise ValueError("identity_invalid")
    if not isinstance(request["stdout_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", request["stdout_sha256"]):
        raise ValueError("digest_invalid")
    paths = request["paths"]
    if not isinstance(paths, list) or not 1 <= len(paths) <= MAX_FILES:
        raise ValueError("paths_invalid")
    for path in paths:
        validate_path(path)
    if len(set(paths)) != len(paths) or len({p.rsplit("/", 1)[1] for p in paths}) != len(paths):
        raise ValueError("duplicate_path_or_name")


def identity(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode, s.st_uid, s.st_nlink)


def read_one(path, remaining):
    directory, name = validate_path(path)
    fds = []
    try:
        tmp = os.open("/tmp", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(tmp)
        parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=tmp)
        fds.append(parent)
        before_parent = os.fstat(parent)
        if before_parent.st_uid != os.getuid() or before_parent.st_mode & 0o022:
            raise ValueError("directory_owner_or_mode")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        fds.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_mode & 0o002:
            raise ValueError("file_owner_mode_or_type")
        if before.st_size > MAX_FILE or before.st_size > remaining:
            raise ValueError("size_limit")
        chunks = []
        budget = min(MAX_FILE, remaining) + 1
        while budget:
            chunk = os.read(fd, min(budget, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            budget -= len(chunk)
        raw = b"".join(chunks)
        after_parent = os.stat(directory, dir_fd=tmp, follow_symlinks=False)
        if (identity(before) != identity(os.fstat(fd))
                or identity(before) != identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
                or identity(before_parent) != identity(after_parent)
                or len(raw) != before.st_size):
            raise ValueError("changed_during_read")
        return {"path": path, "status": "RETRIEVED", "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "data_base64": base64.b64encode(raw).decode(),
                "observed_file": {"device": before.st_dev, "inode": before.st_ino,
                                  "mtime_ns": before.st_mtime_ns, "uid": before.st_uid,
                                  "mode": stat.S_IMODE(before.st_mode)}}
    except FileNotFoundError:
        return {"path": path, "status": "NOT_FOUND", "reason": "missing_at_read"}
    except (OSError, ValueError) as exc:
        return {"path": path, "status": "UNAVAILABLE",
                "reason": str(exc) if isinstance(exc, ValueError) else "filesystem_refused"}
    finally:
        for fd in reversed(fds):
            os.close(fd)


def collect(request):
    validate_request(request)
    entries = []
    remaining = MAX_TOTAL
    for path in request["paths"]:
        item = read_one(path, remaining)
        remaining -= item.get("bytes", 0)
        entries.append(item)
    return {"schema": SCHEMA, "request_sha256": hashlib.sha256(canonical(request)).hexdigest(),
            "files": entries}


def collect_capsule_diagnosis(envelope):
    if (type(envelope) is not dict or set(envelope) != {'schema', 'request'}
            or envelope['schema'] != CAPSULE_DIAG_SCHEMA):
        raise ValueError('capsule_diagnosis_envelope')
    validate_capsule_request(envelope['request'])
    return {'schema': CAPSULE_DIAG_SCHEMA,
            'request_sha256': hashlib.sha256(canonical(envelope)).hexdigest(),
            'result': diagnose_capsule_directories(envelope['request'])}


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise ValueError("request_limit")
        request = strict_json(raw)
        if type(request) is dict and request.get('schema') == CAPSULE_DIAG_SCHEMA:
            action = collect_capsule_diagnosis
        else:
            action = collect_capsule if type(request) is dict and request.get('schema')==CAPSULE_SCHEMA else collect
        sys.stdout.buffer.write(canonical(action(request)))
    except (ValueError, TypeError, RecursionError):
        raise SystemExit(65)
