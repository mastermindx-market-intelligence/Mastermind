#!/usr/bin/env python3
"""Canonical paid GLM private bridge lifecycle behind the installed controller.

This owner starts, stops and observes exactly one fixed paid launchd job. It
never arms Control, never enrolls a credential, never admits a Capacity
worker, never starts a provider task and never modifies the staged disabled
definition, the Control/Worker configs, Capacity or credentials. The launchd
override and registration of the one fixed paid label are the only effects it
can ever produce.

start and stop each require the parent's real privileged-broker owner gate at
entry, and stop requires the parent's real quiescence transport for the
closed-fence acquire/revalidate/release protocol. Both parent helpers are
imported through narrow deferred seams; when the actual parent implementation
is absent this lifecycle refuses and never substitutes a permissive fallback,
a mock, a dictionary-as-authority, a synthetic receipt or a fabricated
journal, marker or store. A modifying call whose effect cannot be proven is
reported as EFFECT_UNKNOWN and is never replayed, cleaned up, compensated,
boot-out-retried or auto-unquiesced. An ambiguous quiesce acquire or release
retains its fence.

status is genuinely read-only: launchctl observation, the qualified definition
bytes and one authenticated read-only readiness probe against the fixed
protected socket. No census of the ordinary bridge principal's UID is
performed anywhere; the bridge principal is an ordinary shared owner, so the
absence of unrelated UID 501 processes is never required, observed or
implied. An occupied incumbent shim owner is never killed, adopted, signalled
or handed off.

The installed-source bootstrap, no-follow/ACL observation and nonce-ACK
socket probe reuse the reviewed structural pattern of the finite lifecycle
source, with paid constants and paid authority only; no finite class,
function or constant is imported or called.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import stat
import subprocess
import sys
import time

WORKER_ID = 'glm-paid-01'
PAID_LABEL = 'com.mastermind.executive.fabric.' + WORKER_ID
PAID_SOCKET_PATH = '/var/run/mastermind-executive/fabric-' + WORKER_ID + '.sock'
PYTHON = '/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12'
BRIDGE_UID = 501
CONTROL_UID = 450
ADAPTER_ID = 'canonical-paid-fabric'
PROFILE_ID = 'fabric.paid.glm.sealed-input.v1'
DEFINITION_PROFILE_ID = 'canonical-paid-fabric'
EXECUTION_SURFACE = 'glm-model-only'
PROFILE_SCHEMA_V2 = 'mastermind.executive_paid_fabric_profile/v2'
READINESS_SCHEMA = 'mastermind.canonical_paid_service_readiness/v1'
QUIESCENCE_SCHEMA = 'mastermind.canonical_paid_quiescence/v1'
INCUMBENT_CONTEXT = 'QUALIFIED_SAME_PROCESS'
PROBE_VERB = '--probe-readiness'
ACTIONS = frozenset({'start', 'stop', 'status'})
_EXPECTED_DEFINITION_FIELDS = frozenset({
    'schema_version', 'adapter_id', 'profile_id', 'execution_surface',
    'release_sha', 'manifest_sha256', 'definition_hashes', 'process',
    'socket', 'adopted', 'incumbent_context',
})
_PROCESS_FIELDS = frozenset({'pid', 'effective_uid', 'effective_gid',
                             'real_uid', 'real_gid', 'start_identity', 'boot_id'})
_REPLY_SOCKET_FIELDS = frozenset({'path', 'device', 'inode', 'uid', 'gid', 'mode'})
_QUIESCENCE_FIELDS = frozenset({'schema_version', 'stop_intent', 'fence_id',
                                'process', 'quiesced', 'broker_process',
                                'receipt_sha256', 'kernel_peer'})
_STOP_INTENT_FIELDS = frozenset({'request_id', 'request_sha256', 'release_sha',
                                 'expected_definition_sha256'})
_BROKER_PROCESS_FIELDS = frozenset({'pid', 'pidversion', 'euid',
                                    'audit_identity_digest', 'boot_id'})
_KERNEL_PEER_FIELDS = frozenset({'euid', 'pid', 'pidversion',
                                 'audit_identity_digest', 'boot_id'})
_REGISTRATION_FIELDS = frozenset({'worker_id', 'quota_class', 'account_label'})
_REMOTE_IDENTITY_FIELDS = frozenset({'worker_uid', 'worker_gid', 'worker_user'})
_RELEASE_RE = re.compile(r'[0-9a-f]{40}')
_DIGEST_RE = re.compile(r'[0-9a-f]{64}')
_NONCE_RE = re.compile(r'[0-9a-f]{32}')
_BOOT_RE = re.compile(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}')
_BOUND_TEXT_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}')
_FIXED_ENV = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'}


class PaidLifecycleError(RuntimeError):
    """Closed, secret-free lifecycle refusal or uncertain-effect report."""

    def __init__(self, code, *, effect_unknown=False):
        self.code = code
        self.effect_unknown = effect_unknown
        super().__init__(code)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _release(value) -> str:
    if type(value) is not str or _RELEASE_RE.fullmatch(value) is None:
        raise PaidLifecycleError('arguments_invalid')
    return value


def _digest256(value) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise PaidLifecycleError('arguments_invalid')
    return value


def definition_aggregate(hashes: dict) -> str:
    """Canonical definition aggregate over the exact four raw file digests.

    The aggregate is the SHA-256 of the canonical JSON encoding of the sorted
    ``filename -> raw file SHA-256`` map, using ``sort_keys`` with compact
    separators and NO trailing newline, matching the paid wire digest.
    Document serialization remains distinct from this identity digest.
    """
    if (type(hashes) is not dict or not hashes
            or any(type(key) is not str or type(item) is not str
                   or _DIGEST_RE.fullmatch(item) is None
                   for key, item in hashes.items())):
        raise PaidLifecycleError('definition_digests_invalid')
    canonical = (json.dumps(dict(sorted(hashes.items())), sort_keys=True,
                            separators=(',', ':'), ensure_ascii=False,
                            allow_nan=False)).encode('utf-8')
    return digest(canonical)


def checked_command(argv, *, allowed=(0,)):
    """One bounded fixed argv under a closed environment; never a caller field."""
    if (type(argv) is not list
            or any(type(item) is not str or not item or len(item) > 4096
                   or any(ord(char) < 32 for char in item) for item in argv)):
        raise PaidLifecycleError('native_command_invalid')
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                                timeout=15, check=False, env=dict(_FIXED_ENV))
    except (OSError, subprocess.SubprocessError) as exc:
        raise PaidLifecycleError('native_command_unavailable') from exc
    if (result.returncode not in allowed or len(result.stdout) > 262144
            or len(result.stderr) > 262144):
        raise PaidLifecycleError('native_command_failed')
    return result


def protected(path, directory=False):
    """Every ancestor and the leaf are root-owned, unmutable and unlinked."""
    for item in (path, *path.parents):
        info = item.lstat()
        is_dir = directory or item != path
        if (info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISDIR(info.st_mode) if is_dir else stat.S_ISREG(info.st_mode))):
            raise PaidLifecycleError('untrusted_installation_source')


def verify_release_before_import(commit, manifest_digest):
    """Prove this exact installed release before any release package import.

    Same structural pattern as the reviewed finite bootstrap: no release
    package import occurs before the manifest digest, the whole declared
    inventory, every object's owner/mode/ACL and the pinned stdlib-only ACL
    observer have been validated from held bytes. This grants no release or
    launch authority by itself.
    """
    release_root = Path('/Library/Application Support/MastermindExecutive') / 'releases' / commit
    if Path(__file__).absolute() != release_root / 'ops/executive_os/canonical_paid_lifecycle.py':
        raise PaidLifecycleError('fixed_installed_lifecycle_entry_required')
    protected(Path(__file__).absolute())
    protected(release_root, directory=True)
    manifest = release_root / '.executive-release-manifest.json'
    protected(manifest)
    manifest_bytes = manifest.read_bytes()
    if digest(manifest_bytes) != manifest_digest:
        raise PaidLifecycleError('release_manifest_changed')
    document = json.loads(manifest_bytes)
    if (document.get('commit_sha') != commit
            or _RELEASE_RE.fullmatch(str(document.get('tree_sha'))) is None):
        raise PaidLifecycleError('release_identity_changed')
    rows = {row['path']: row for row in document['entries']}
    acl_path = release_root / 'control_plane/fs_security.py'
    protected(acl_path)
    acl_bytes = acl_path.read_bytes()
    if digest(acl_bytes) != rows['control_plane/fs_security.py']['sha256']:
        raise PaidLifecycleError('acl_observer_changed')
    acl_scope = {'__name__': '_fixed_canonical_paid_acl_bootstrap', '__file__': str(acl_path)}
    exec(compile(acl_bytes, str(acl_path), 'exec'), acl_scope)
    has_acl = acl_scope['has_macos_acl']
    entry = Path(__file__).absolute()
    for path in (entry, *entry.parents, release_root, *release_root.parents, manifest):
        if has_acl(path, expected_identity=path.lstat()):
            raise PaidLifecycleError('untrusted_installation_acl')
    seen = set()
    for directory, names, files in os.walk(release_root, followlinks=False):
        for name in names + files:
            path = Path(directory) / name
            relative = path.relative_to(release_root).as_posix()
            if relative == '.executive-release-manifest.json':
                continue
            row = rows[relative]
            info = path.lstat()
            if (info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022
                    or has_acl(path, expected_identity=info,
                               allow_symlink=stat.S_ISLNK(info.st_mode))):
                raise PaidLifecycleError('untrusted_release_object')
            if stat.S_IMODE(info.st_mode) != row['mode']:
                raise PaidLifecycleError('release_mode_changed')
            if row['type'] == 'file':
                if (not stat.S_ISREG(info.st_mode)
                        or digest(path.read_bytes()) != row['sha256']):
                    raise PaidLifecycleError('release_code_changed')
            elif row['type'] == 'directory':
                if not stat.S_ISDIR(info.st_mode):
                    raise PaidLifecycleError('release_directory_changed')
            elif row['type'] == 'symlink':
                if (not stat.S_ISLNK(info.st_mode) or os.readlink(path) != row['target']
                        or not path.resolve().is_relative_to(release_root)):
                    raise PaidLifecycleError('release_link_changed')
            else:
                raise PaidLifecycleError('unsupported_release_object')
            seen.add(relative)
    if seen != set(rows):
        raise PaidLifecycleError('release_inventory_changed')
    sys.path.insert(0, str(release_root))
    from ops.executive_os.release_manifest import verify
    verify(release_root, commit, document['tree_sha'])
    return document


def paid_identity():
    """Frozen paid constants cross-checked against the provided inert module."""
    from ops.executive_os.canonical_paid_definition import (
        DESTINATION, FILES, PAID_BRIDGE_UID, PAID_LABEL, PAID_SOCKET_PATH)
    from ops.executive_os.capacity_broker_topology import PYTHON_BINARY
    identity = {
        'label': PAID_LABEL, 'socket': PAID_SOCKET_PATH,
        'definition': Path(DESTINATION), 'plist': Path(DESTINATION) / (PAID_LABEL + '.plist'),
        'files': frozenset(FILES), 'bridge_uid': PAID_BRIDGE_UID,
        'python': str(PYTHON_BINARY),
    }
    if (identity['label'] != PAID_LABEL or identity['socket'] != PAID_SOCKET_PATH
            or identity['bridge_uid'] != BRIDGE_UID or identity['python'] != PYTHON
            or len(identity['files']) != 4):
        raise PaidLifecycleError('paid_identity_pins_diverged')
    return identity


def protected_bytes(path, *, mode=0o444, gid=0):
    """Root read through the existing owner's no-follow/ACL file reader."""
    from ops.executive_os import autonomy_control as owner
    from control_plane.fs_security import has_macos_acl
    for parent in path.parents:
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022 or has_macos_acl(parent, expected_identity=info)):
            raise PaidLifecycleError('untrusted_definition_ancestor')
    raw, _info = owner._read_root_file(path, modes=frozenset({mode}), uid=0, gid=gid)
    return raw


def parse_registration(raw, *, label, plist_path):
    """Require one top-level fixed launchd job and unambiguous PID/state/path."""
    if (type(raw) is not str or plist_path is None
            or len(raw.encode()) > 262144 or '\x00' in raw):
        raise PaidLifecycleError('launchd_output_invalid')
    expected_path = str(plist_path)
    lines = raw.splitlines()
    if (not lines
            or re.fullmatch(r'system/' + re.escape(label) + r' = \{', lines[0]) is None):
        raise PaidLifecycleError('launchd_label_mismatch')
    fields = {}
    depth = 0
    for line in lines:
        if depth == 1 and line.startswith('\t') and not line.startswith('\t\t'):
            match = re.fullmatch(r'\t(state|pid|path) = (.+)', line)
            if match:
                key, value = match.groups()
                if key in fields:
                    raise PaidLifecycleError('launchd_duplicate_field')
                fields[key] = value
        depth += line.count('{') - line.count('}')
        if depth < 0:
            raise PaidLifecycleError('launchd_structure_invalid')
    if depth != 0 or fields.get('path') != expected_path:
        raise PaidLifecycleError('launchd_path_mismatch')
    state = fields.get('state')
    pid = fields.get('pid')
    if state == 'running' and pid and re.fullmatch(r'[1-9][0-9]{0,9}', pid):
        return dict(state='running', pid=int(pid))
    if state in {'waiting', 'not running', 'spawn scheduled'} and pid is None:
        return dict(state='registered', pid=None)
    raise PaidLifecycleError('launchd_state_unqualified')


def parse_override(raw, *, label):
    """The one fixed label's disabled-state override; default when unlisted."""
    if type(raw) is not str or len(raw.encode()) > 262144 or '\x00' in raw:
        raise PaidLifecycleError('launchd_override_invalid')
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) < 2 or lines[0] != 'disabled services = {' or lines[-1] != '}':
        raise PaidLifecycleError('launchd_override_invalid')
    rows = {}
    for line in lines[1:-1]:
        match = re.fullmatch(r'"([A-Za-z0-9._-]+)" => (enabled|disabled|true|false)', line)
        if not match or match[1] in rows:
            raise PaidLifecycleError('launchd_override_invalid')
        rows[match[1]] = match[2]
    value = rows.get(label)
    return 'default' if value is None else 'disabled' if value in {'disabled', 'true'} else 'enabled'


def socket_identity(info) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def socket_acl_absent(path, before):
    """Observe this socket's own ACL without opening or connecting to it.

    Only native NULL+ENOENT with an unchanged full socket identity proves no
    allocated extended ACL. Any allocated ACL or other API result fails
    closed. Read-only: the socket is never opened or connected here.
    """
    if not (sys.platform == 'darwin' and stat.S_ISSOCK(before.st_mode)):
        raise PaidLifecycleError('socket_acl_platform_or_type')
    if socket_identity(path.lstat()) != socket_identity(before):
        raise PaidLifecycleError('socket_acl_identity_changed')
    lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    get_acl, free_acl = lib.acl_get_link_np, lib.acl_free
    get_acl.argtypes = [ctypes.c_char_p, ctypes.c_int]
    get_acl.restype = ctypes.c_void_p
    free_acl.argtypes = [ctypes.c_void_p]
    free_acl.restype = ctypes.c_int
    ctypes.set_errno(0)
    acl = get_acl(os.fsencode(path), 0x100)
    observed_errno = ctypes.get_errno()
    if acl:
        if free_acl(acl) != 0:
            raise PaidLifecycleError('socket_acl_free_failed')
        raise PaidLifecycleError('socket_allocated_acl')
    if observed_errno != errno.ENOENT:
        raise PaidLifecycleError('socket_acl_observation_unknown')
    if socket_identity(path.lstat()) != socket_identity(before):
        raise PaidLifecycleError('socket_acl_identity_changed')


def observed_socket_state():
    """Read-only fixed-socket presence and identity; never connects."""
    path = Path(PAID_SOCKET_PATH)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PaidLifecycleError('socket_observation_unavailable') from exc
    if not stat.S_ISSOCK(info.st_mode):
        raise PaidLifecycleError('socket_path_occupied')
    return socket_identity(info)


# Fixed incumbent owner state, shared with the real shim constructor. No credential
# is opened. This is an absence observation, never an idle/adoption authorization.
INCUMBENT_LOCK = Path('/Users/chriswong/.claude/projects/'
    '-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/'
    'meta-ceo-b-2026-09-08/ext/glm_shim/shim.lock')


def require_incumbent_absent():
    """Momentarily observe the existing singleton and HTTP listener absent.

    No missing PID/lock file proves absence. Do not create/truncate/delete any
    incumbent state. A race after this temporary observation is still fenced by
    the canonical owner's actual singleton acquisition; ambiguous launch is held.
    """
    import fcntl
    fd = None
    try:
        fd = os.open(INCUMBENT_LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                     | getattr(os, 'O_CLOEXEC', 0))
        held = os.fstat(fd)
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                    info.st_gid, info.st_nlink)
        if (not stat.S_ISREG(held.st_mode) or held.st_uid != BRIDGE_UID
                or stat.S_IMODE(held.st_mode) != 0o600 or held.st_nlink != 1
                or identity(held) != identity(INCUMBENT_LOCK.lstat())):
            raise PaidLifecycleError('incumbent_absence_unknown')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = checked_command(['/usr/sbin/lsof', '-nP', '-iTCP:4141',
                                  '-sTCP:LISTEN', '-F', 'p'], allowed=(0, 1))
        if result.returncode != 1 or result.stdout or result.stderr:
            raise PaidLifecycleError('incumbent_present_or_unknown')
        if (identity(os.fstat(fd)) != identity(held)
                or identity(INCUMBENT_LOCK.lstat()) != identity(held)):
            raise PaidLifecycleError('incumbent_absence_changed')
    except (OSError, ValueError) as exc:
        raise PaidLifecycleError('incumbent_present_or_unknown') from exc
    finally:
        if fd is not None:
            os.close(fd)


def _bind_live_peer(connection, reply):
    """Bind this response to the actual connected Darwin process.

    Darwin LOCAL_PEERTOKEN follows the peer socket's last process, unlike
    cached listen credentials, so it is captured only after the server has
    answered and before the nonce ACK while its readiness-only ACK wait keeps
    this exact connection alive. No getpeereid-only shortcut is used.
    """
    from control_plane.executive_peer_identity import (
        capture_peer_identity, _current_capture)
    peer = capture_peer_identity(connection)
    process = reply.get('process')
    if (type(process) is not dict or type(process.get('pid')) is not int
            or peer.euid != BRIDGE_UID or peer.pid != process['pid']
            or type(getattr(peer, 'pidversion', None)) is not int
            or peer.pidversion <= 0
            or _DIGEST_RE.fullmatch(str(getattr(peer, 'audit_identity_digest', ''))) is None):
        raise PaidLifecycleError('connected_process_mismatch')
    _current_capture(peer)
    return peer


def probe_paid_socket():
    """One authenticated Control-side read of the paid service; no effect.

    Runs only as the fixed Control principal with closed supplementary groups.
    Sends the exact readiness request with a fresh 32-lowerhex nonce, requires
    the standard broker envelope with the matching nonce, validates the
    canonical paid readiness payload shape, captures the actual LOCAL_peer
    token after the response and before the nonce ACK, re-proves the socket
    identity and ACL, and only then delivers the nonce ACK.
    """
    import socket
    from control_plane.executive_worker_broker import (
        BROKER_REQUEST_SCHEMA_VERSION, BROKER_RESPONSE_SCHEMA_VERSION)
    from control_plane.executive_fabric_bridge_broker import _strict_json
    if (os.getuid(), os.geteuid(), os.getgid(), os.getegid()) != (
            CONTROL_UID, CONTROL_UID, CONTROL_UID, CONTROL_UID):
        raise PaidLifecycleError('control_probe_principal_invalid')
    if set(os.getgroups()) - {CONTROL_UID}:
        raise PaidLifecycleError('control_probe_groups_invalid')
    identity = paid_identity()
    path = Path(identity['socket'])
    before = path.lstat()
    if (not stat.S_ISSOCK(before.st_mode)
            or (before.st_uid, before.st_gid, stat.S_IMODE(before.st_mode),
                before.st_nlink) != (0, CONTROL_UID, 0o660, 1)):
        raise PaidLifecycleError('activated_socket_invalid')
    socket_acl_absent(path, before)
    nonce = secrets.token_hex(16)
    if _NONCE_RE.fullmatch(nonce) is None:
        raise PaidLifecycleError('readiness_nonce_invalid')
    request = dict(schema_version=BROKER_REQUEST_SCHEMA_VERSION,
                   request_id='canonical-paid-readiness-' + nonce,
                   operation='service-readiness', payload={'nonce': nonce})
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(identity['socket'])
        connection.sendall(json.dumps(request, separators=(',', ':')).encode() + b'\n')
        raw = bytearray()
        while len(raw) <= 65536 and not raw.endswith(b'\n'):
            part = connection.recv(min(4096, 65537 - len(raw)))
            if not part:
                raise PaidLifecycleError('readiness_response_incomplete')
            raw.extend(part)
        if len(raw) > 65536 or bytes(raw).count(b'\n') != 1:
            raise PaidLifecycleError('readiness_response_invalid')
        response = _strict_json(bytes(raw))
        if (type(response) is not dict
                or set(response) != {'schema_version', 'request_id', 'operation',
                                     'ok', 'result'}
                or response['schema_version'] != BROKER_RESPONSE_SCHEMA_VERSION
                or response['request_id'] != request['request_id']
                or response['operation'] != 'service-readiness'
                or response['ok'] is not True or type(response['result']) is not dict
                or response['result'].get('nonce') != nonce):
            raise PaidLifecycleError('readiness_response_mismatch')
        _validate_readiness_payload(response['result'], identity)
        reply = {key: value for key, value in response['result'].items()
                 if key != 'nonce'}
        # Captured AFTER the server sent and BEFORE its nonce ACK returns.
        peer = _bind_live_peer(connection, reply)
        after = path.lstat()
        if socket_identity(before) != socket_identity(after):
            raise PaidLifecycleError('socket_generation_changed')
        socket_acl_absent(path, after)
        reply['kernel_peer'] = dict(euid=peer.euid, pid=peer.pid,
                                    pidversion=peer.pidversion,
                                    audit_identity_digest=peer.audit_identity_digest)
        connection.sendall(nonce.encode('ascii') + b'\n')
        return reply


def _validate_readiness_payload(result, identity, extra=frozenset({'nonce'})):
    """Closed-shape check of the canonical paid readiness payload.

    The Control-side probe admits exactly the nonce field; the root host
    admits exactly the locally captured kernel_peer field.
    """
    if (type(result) is not dict
            or set(result) != _EXPECTED_DEFINITION_FIELDS | set(extra)):
        raise PaidLifecycleError('readiness_payload_shape_invalid')
    if (result['schema_version'] != READINESS_SCHEMA
            or result['adapter_id'] != ADAPTER_ID or result['profile_id'] != PROFILE_ID
            or result['execution_surface'] != EXECUTION_SURFACE
            or result['incumbent_context'] != INCUMBENT_CONTEXT):
        raise PaidLifecycleError('readiness_payload_identity_invalid')
    if (type(result['release_sha']) is not str
            or _RELEASE_RE.fullmatch(result['release_sha']) is None
            or type(result['manifest_sha256']) is not str
            or _DIGEST_RE.fullmatch(result['manifest_sha256']) is None):
        raise PaidLifecycleError('readiness_payload_release_invalid')
    hashes = result['definition_hashes']
    if (type(hashes) is not dict or set(hashes) != set(identity['files'])
            or any(type(value) is not str or _DIGEST_RE.fullmatch(value) is None
                   for value in hashes.values())):
        raise PaidLifecycleError('readiness_payload_definition_invalid')
    process = result['process']
    if (type(process) is not dict or set(process) != _PROCESS_FIELDS
            or type(process['pid']) is not int or not 0 < process['pid'] < 2 ** 31
            or any(type(process[key]) is not int or process[key] < 0 for key in (
                'effective_uid', 'effective_gid', 'real_uid', 'real_gid'))
            or type(process['start_identity']) is not str or not process['start_identity']
            or len(process['start_identity']) > 128
            or process['start_identity'].startswith('darwin:')
            or type(process['boot_id']) is not str
            or _BOOT_RE.fullmatch(process['boot_id']) is None):
        raise PaidLifecycleError('readiness_payload_process_invalid')
    reply_socket = result['socket']
    if (type(reply_socket) is not dict or set(reply_socket) != _REPLY_SOCKET_FIELDS
            or reply_socket['path'] != identity['socket']
            or any(type(reply_socket[key]) is not int or reply_socket[key] < 0
                   for key in ('device', 'inode', 'uid', 'gid', 'mode'))
            or reply_socket['uid'] != 0 or reply_socket['gid'] != CONTROL_UID
            or reply_socket['mode'] & 0o7777 != 0o660):
        raise PaidLifecycleError('readiness_payload_socket_invalid')
    adopted = result['adopted']
    if (type(adopted) is not dict or set(adopted) != {'device', 'inode'}
            or any(type(adopted[key]) is not int or adopted[key] <= 0
                   for key in ('device', 'inode'))):
        raise PaidLifecycleError('readiness_payload_adopted_invalid')


def _require_paid_lifecycle_owner(action, release_sha, definition_sha):
    """Parent privileged-broker owner gate; imported, never reimplemented.

    This seam imports the parent's real ``require_paid_lifecycle_owner`` and
    gives it only the three closed arguments. It validates the actual
    production broker origin, the private context and the current durable
    in-flight request; no caller boolean, environment or role label is ever a
    substitute, and a missing parent implementation is a refusal.
    """
    try:
        from control_plane.executive_privileged_broker import require_paid_lifecycle_owner
    except Exception as exc:
        raise PaidLifecycleError('parent_owner_helper_unavailable') from exc
    if type(require_paid_lifecycle_owner) is not type(_require_paid_lifecycle_owner):
        raise PaidLifecycleError('parent_owner_helper_unavailable')
    try:
        require_paid_lifecycle_owner(action, release_sha, definition_sha)
    except Exception as exc:
        raise PaidLifecycleError('parent_owner_refused') from exc


def _quiesce_paid_service(phase, release_sha, definition_sha, *, fence=None):
    """Parent quiescence transport; imported, never reimplemented or stubbed."""
    if phase not in {'acquire', 'revalidate', 'release'}:
        raise PaidLifecycleError('quiesce_phase_invalid')
    if ((phase == 'acquire' and fence is not None)
            or (phase != 'acquire' and (type(fence) is not str
                or _DIGEST_RE.fullmatch(fence) is None))):
        raise PaidLifecycleError('quiesce_fence_invalid')
    try:
        from control_plane.paid_quiesce_transport import quiesce_paid_service
    except Exception as exc:
        raise PaidLifecycleError('parent_quiesce_helper_unavailable') from exc
    if type(quiesce_paid_service) is not type(_quiesce_paid_service):
        raise PaidLifecycleError('parent_quiesce_helper_unavailable')
    try:
        return quiesce_paid_service(phase, release_sha, definition_sha, fence=fence)
    except Exception as exc:
        # Parent may have issued the fence before a transport failure.
        raise PaidLifecycleError('parent_quiesce_unconfirmed', effect_unknown=True) from exc


def _release_own_fence(acquired, release_sha, definition_sha):
    """Release only the exact confirmed issuer/fence/intent before launchctl.

    An ambiguous transport/reply leaves the original operation UNKNOWN. This
    does not grant a caller a release capability: the parent rederives its real
    original request and read-only inflight FD on each call.
    """
    try:
        held = _validate_quiescence_receipt(acquired, release_sha, definition_sha)
        reply = _quiesce_paid_service('release', release_sha, definition_sha,
                                      fence=held['fence_id'])
        validated = _validate_quiescence_receipt(reply, release_sha, definition_sha)
        return validated == held
    except Exception:
        return False


def _validate_quiescence_receipt(reply, release_sha, definition_sha):
    """Closed-shape validation of one parent quiescence receipt."""
    if type(reply) is not dict or set(reply) != _QUIESCENCE_FIELDS:
        raise PaidLifecycleError('quiesce_receipt_shape_invalid')
    if reply['schema_version'] != QUIESCENCE_SCHEMA or reply['quiesced'] is not True:
        raise PaidLifecycleError('quiesce_receipt_identity_invalid')
    if (type(reply['fence_id']) is not str
            or _DIGEST_RE.fullmatch(reply['fence_id']) is None
            or type(reply['receipt_sha256']) is not str
            or _DIGEST_RE.fullmatch(reply['receipt_sha256']) is None):
        raise PaidLifecycleError('quiesce_receipt_identity_invalid')
    intent = reply['stop_intent']
    if (type(intent) is not dict or set(intent) != _STOP_INTENT_FIELDS
            or type(intent['request_id']) is not str
            or _BOUND_TEXT_RE.fullmatch(intent['request_id']) is None
            or type(intent['request_sha256']) is not str
            or _DIGEST_RE.fullmatch(intent['request_sha256']) is None
            or intent['release_sha'] != release_sha
            or intent['expected_definition_sha256'] != definition_sha):
        raise PaidLifecycleError('quiesce_receipt_intent_invalid')
    process = reply['process']
    if (type(process) is not dict or set(process) != _PROCESS_FIELDS
            or type(process['pid']) is not int or not 0 < process['pid'] < 2 ** 31
            or any(type(process[key]) is not int or process[key] < 0 for key in (
                'effective_uid', 'effective_gid', 'real_uid', 'real_gid'))
            or type(process['start_identity']) is not str or not process['start_identity']
            or len(process['start_identity']) > 128
            or process['start_identity'].startswith('darwin:')
            or type(process['boot_id']) is not str
            or _BOOT_RE.fullmatch(process['boot_id']) is None):
        raise PaidLifecycleError('quiesce_receipt_process_invalid')
    broker = reply['broker_process']
    if (type(broker) is not dict or set(broker) != _BROKER_PROCESS_FIELDS
            or type(broker['pid']) is not int or not 0 < broker['pid'] < 2 ** 31
            or type(broker['pidversion']) is not int or broker['pidversion'] <= 0
            or broker['euid'] != 0
            or type(broker['audit_identity_digest']) is not str
            or _DIGEST_RE.fullmatch(broker['audit_identity_digest']) is None
            or type(broker['boot_id']) is not str
            or _BOOT_RE.fullmatch(broker['boot_id']) is None):
        raise PaidLifecycleError('quiesce_receipt_broker_invalid')
    peer = reply['kernel_peer']
    if (type(peer) is not dict or set(peer) != _KERNEL_PEER_FIELDS
            or type(peer['pid']) is not int or not 0 < peer['pid'] < 2 ** 31
            or type(peer['pidversion']) is not int or peer['pidversion'] <= 0
            or peer['euid'] != BRIDGE_UID
            or type(peer['audit_identity_digest']) is not str
            or _DIGEST_RE.fullmatch(peer['audit_identity_digest']) is None
            or type(peer['boot_id']) is not str
            or _BOOT_RE.fullmatch(peer['boot_id']) is None):
        raise PaidLifecycleError('quiesce_receipt_peer_invalid')
    return reply


def _verify_qualified_artifacts(artifacts):
    """Mechanical seam for the parent-owned pure v2 qualification verifier.

    This only imports and calls the separately implemented public interface
    ``verify_qualified_artifacts(artifacts) -> {profile, hashes, bindings}``.
    The v2 verifier is never duplicated, weakened or reinterpreted here, and
    tests may substitute only this explicit mechanical namespace seam while
    reporting that the substitution carries no authentication.
    """
    from ops.executive_os.canonical_paid_qualification import verify_qualified_artifacts
    return verify_qualified_artifacts(artifacts)


def _validate_profile_pins(profile, identity, expected_sha):
    """Only the pins this lifecycle's own authority depends on; no v2 dupe."""
    if (type(profile) is not dict
            or profile.get('schema_version') != PROFILE_SCHEMA_V2
            or profile.get('profile_id') != DEFINITION_PROFILE_ID
            or profile.get('worker_id') != WORKER_ID
            or profile.get('bridge_uid') != identity['bridge_uid']
            or profile.get('bridge_armed') is not False
            or profile.get('capacity_admitted') is not False
            or profile.get('socket_path') != identity['socket']
            or profile.get('label') != identity['label']
            or profile.get('release_commit') != expected_sha):
        raise PaidLifecycleError('qualified_profile_pin_differs')
    registration = profile.get('registration')
    if (type(registration) is not dict or set(registration) != _REGISTRATION_FIELDS
            or any(type(value) is not str or not value or len(value) > 128
                   for value in registration.values())):
        raise PaidLifecycleError('qualified_registration_shape_invalid')
    if (type(profile.get('bindings_sha256')) is not str
            or _DIGEST_RE.fullmatch(profile['bindings_sha256']) is None
            or type(profile.get('expected_remote_binary')) is not dict):
        raise PaidLifecycleError('qualified_profile_shape_invalid')
    remote = profile.get('remote_worker_identity')
    if (type(remote) is not dict or set(remote) != _REMOTE_IDENTITY_FIELDS
            or type(remote['worker_uid']) is not int or remote['worker_uid'] < 0
            or type(remote['worker_gid']) is not int or remote['worker_gid'] < 0
            or type(remote['worker_user']) is not str or not remote['worker_user']):
        raise PaidLifecycleError('qualified_remote_identity_shape_invalid')


def _require_control_profile_joins(control, profile, principal, definition, hashes):
    """Pure joins of actual owner observations; none is caller authority."""
    if any(profile.get(key) != value for key, value in principal.items()):
        raise PaidLifecycleError('qualified_principal_changed')
    expected = dict(bindings_path=str(definition / 'bindings.json'),
                    bindings_sha256=hashes['bindings.json'])
    if control.get('canonical_paid_fabric') != expected:
        raise PaidLifecycleError('control_paid_binding_changed')


class ProductionHost:
    """Root production host; tests substitute it, never production verdicts."""

    def __init__(self, expected_definition_sha256):
        self.definition_sha = _digest256(expected_definition_sha256)
        self.sha = None
        self.owner = None
        self.manifest_digest = None
        self.lock_fd = None

    @contextmanager
    def qualified_interval(self, expected_sha):
        """The incumbent CONFIG_ROOT mutex, acquired without waiting."""
        import fcntl
        if os.geteuid() != 0 or sys.platform != 'darwin':
            raise PaidLifecycleError('root_darwin_required')
        from ops.executive_os import autonomy_control as owner
        self.sha = _release(expected_sha)
        self.owner = owner.ProductionCeoSubmitHost()
        self.owner.require_transaction_absent()
        self.owner._config_root_safe()
        fd = os.open(owner.CONFIG_ROOT, os.O_RDONLY | os.O_DIRECTORY
                     | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0))
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise PaidLifecycleError('config_publication_mutex_occupied') from exc
            held, visible = os.fstat(fd), Path(owner.CONFIG_ROOT).lstat()
            if ((held.st_dev, held.st_ino) != (visible.st_dev, visible.st_ino)
                    or held.st_uid != 0 or held.st_gid != 0
                    or stat.S_IMODE(held.st_mode) != 0o755):
                raise PaidLifecycleError('config_lock_identity_changed')
            self.owner._config_root_safe()
            self.owner.require_transaction_absent()
            self.lock_fd = fd
            yield self.qualify()
        finally:
            self.lock_fd = None
            os.close(fd)

    def qualify(self):
        """Re-qualify release, configs, definition and qualification snapshot."""
        from control_plane.fs_security import has_macos_acl
        from ops.executive_os import autonomy_control as owner
        identity = paid_identity()
        from ops.executive_os import canonical_paid_definition as base
        if self.lock_fd is None:
            raise PaidLifecycleError('config_mutex_not_held')
        base._trusted_control_root(self.lock_fd)
        principal = base._qualify_bridge_principal()
        if self.owner.require_exact_install(self.sha) != self.sha:
            raise PaidLifecycleError('installed_release_changed')
        self.owner.require_transaction_absent()
        self.owner.require_services_already_stopped()
        self.owner.require_service_uids_quiescent()
        prior = self.owner.load_unarmed_configs(self.sha)
        if (any(prior.control.get(key) is not False for key in (
                'ceo_submit_armed', 'coo_autonomy_armed', 'coo_operator_harness_armed',
                'fabric_bridge_armed', 'coo_foreground_only'))
                or prior.worker.get('operator_harness_armed') is not False):
            raise PaidLifecycleError('configs_not_wholly_disarmed')
        self.owner.require_runtime_quiescent(prior)
        release_root = Path(owner.SYSTEM_ROOT) / 'releases' / self.sha
        manifest_bytes = protected_bytes(release_root / '.executive-release-manifest.json')
        self.manifest_digest = digest(manifest_bytes)
        definition = identity['definition']
        info = definition.lstat()
        if (not stat.S_ISDIR(info.st_mode)
                or (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (0, 0, 0o755)
                or info.st_nlink != 2
                or has_macos_acl(definition, expected_identity=info)):
            raise PaidLifecycleError('untrusted_definition_directory')
        if set(os.listdir(definition)) != set(identity['files']):
            raise PaidLifecycleError('definition_inventory_changed')
        artifacts = {}
        for name in sorted(identity['files']):
            path = definition / name
            file_info = path.lstat()
            if (not stat.S_ISREG(file_info.st_mode) or file_info.st_nlink != 1
                    or (file_info.st_uid, file_info.st_gid) != (0, 0)
                    or stat.S_IMODE(file_info.st_mode) != 0o444
                    or has_macos_acl(path, expected_identity=file_info)):
                raise PaidLifecycleError('untrusted_definition_artifact')
            artifacts[name] = protected_bytes(path)
        qualification = _verify_qualified_artifacts(dict(artifacts))
        if (type(qualification) is not dict
                or set(qualification) != {'profile', 'hashes', 'bindings'}
                or type(qualification['profile']) is not dict
                or type(qualification['bindings']) is not list
                or type(qualification['hashes']) is not dict):
            raise PaidLifecycleError('qualification_unavailable')
        hashes = {name: digest(artifacts[name]) for name in sorted(artifacts)}
        if qualification['hashes'] != hashes:
            raise PaidLifecycleError('qualified_hashes_differ')
        _validate_profile_pins(qualification['profile'], identity, self.sha)
        _require_control_profile_joins(prior.control, qualification['profile'],
                                       principal, definition, hashes)
        plist = plistlib.loads(artifacts[identity['label'] + '.plist'])
        if (plist.get('Label') != identity['label'] or plist.get('Disabled') is not True
                or plist.get('RunAtLoad') is not False):
            raise PaidLifecycleError('canonical_paid_definition_must_stay_disabled')
        if definition_aggregate(hashes) != self.definition_sha:
            raise PaidLifecycleError('definition_aggregate_changed')
        return dict(release_sha=self.sha, manifest_sha256=self.manifest_digest,
                    definition_sha256=self.definition_sha, definition_hashes=hashes,
                    profile=qualification['profile'], bindings_rows=len(qualification['bindings']),
                    control_sha256=prior.control_sha256, worker_sha256=prior.worker_sha256,
                    python_image=str(Path(identity['python']).resolve(strict=True)))

    def recheck(self, snapshot):
        if self.qualify() != snapshot:
            raise PaidLifecycleError('protected_generation_changed')

    def require_incumbent_absent(self):
        require_incumbent_absent()

    def registration(self):
        identity = paid_identity()
        result = checked_command(['/bin/launchctl', 'print', 'system/' + identity['label']],
                                 allowed=(0, 113))
        if result.returncode == 113:
            return dict(state='absent', pid=None)
        return parse_registration(result.stdout.decode('utf-8', 'strict'),
                                  label=identity['label'], plist_path=identity['plist'])

    def override(self):
        identity = paid_identity()
        return parse_override(
            checked_command(['/bin/launchctl', 'print-disabled', 'system'])
            .stdout.decode('utf-8', 'strict'), label=identity['label'])

    def modify(self, verb):
        """Only the five fixed launchd verbs with fully bounded fixed argv."""
        if verb not in {'enable', 'disable', 'bootstrap', 'kickstart', 'bootout'}:
            raise PaidLifecycleError('unknown_fixed_verb')
        identity = paid_identity()
        argv = (['/bin/launchctl', 'bootstrap', 'system', str(identity['plist'])]
                if verb == 'bootstrap'
                else ['/bin/launchctl', verb, 'system/' + identity['label']])
        checked_command(argv)

    @staticmethod
    def pause():
        time.sleep(1)

    def require_idle(self, snapshot):
        """Runtime quiescence only; no census of the ordinary bridge UID."""
        del snapshot
        prior = self.owner.load_unarmed_configs(self.sha)
        self.owner.require_runtime_quiescent(prior)

    def readiness(self, snapshot, registration):
        """Bracket the launchd PID around one read-only Control probe."""
        from control_plane.darwin_process_image import inspect_owned_darwin_image
        from ops.executive_os import autonomy_control as owner
        identity = paid_identity()
        if registration['state'] != 'running':
            raise PaidLifecycleError('registered_not_ready')
        pid = registration['pid']
        before = inspect_owned_darwin_image(pid)
        result = checked_command([
            '/usr/bin/sudo', '-u', owner.CONTROL_USER, '/usr/bin/env', '-i',
            'HOME=' + str(Path(owner.RUNTIME_ROOT) / 'control' / 'home'),
            'PATH=' + _FIXED_ENV['PATH'], 'LANG=C', 'LC_ALL=C', PYTHON, '-I', '-S', '-B',
            str(Path(__file__).absolute()), PROBE_VERB,
            '--expected-sha', self.sha,
            '--expected-manifest-sha256', self.manifest_digest])
        try:
            reply = json.loads(result.stdout)
        except (UnicodeError, ValueError) as exc:
            raise PaidLifecycleError('readiness_output_invalid') from exc
        after = inspect_owned_darwin_image(pid)
        if before != after:
            raise PaidLifecycleError('readiness_generation_changed')
        profile = snapshot['profile']
        if (type(reply) is not dict
                or set(reply) != _EXPECTED_DEFINITION_FIELDS | {'kernel_peer'}
                or reply['schema_version'] != READINESS_SCHEMA
                or reply['adapter_id'] != ADAPTER_ID or reply['profile_id'] != PROFILE_ID
                or reply['execution_surface'] != EXECUTION_SURFACE
                or reply['incumbent_context'] != INCUMBENT_CONTEXT):
            raise PaidLifecycleError('same_generation_readiness_mismatch')
        _validate_readiness_payload(reply, identity, extra=frozenset({'kernel_peer'}))
        kernel_peer = reply['kernel_peer']
        if (type(kernel_peer) is not dict
                or set(kernel_peer) != {'euid', 'pid', 'pidversion', 'audit_identity_digest'}
                or kernel_peer['euid'] != identity['bridge_uid']
                or kernel_peer['pid'] != pid
                or kernel_peer['pidversion'] != before['exec_instance']['pidversion']
                or type(kernel_peer['audit_identity_digest']) is not str
                or _DIGEST_RE.fullmatch(kernel_peer['audit_identity_digest']) is None):
            raise PaidLifecycleError('same_generation_readiness_mismatch')
        process = reply['process']
        if (reply['release_sha'] != snapshot['release_sha']
                or reply['manifest_sha256'] != snapshot['manifest_sha256']
                or reply['definition_hashes'] != snapshot['definition_hashes']
                or process['pid'] != pid
                or process['effective_uid'] != identity['bridge_uid']
                or process['real_uid'] != identity['bridge_uid']
                or process['effective_gid'] != profile['bridge_gid']
                or process['real_gid'] != profile['bridge_gid']
                or process['start_identity'] != before['start_identity']
                or process['boot_id'] != before['boot_id']
                or before['executable_path'] != snapshot['python_image']):
            raise PaidLifecycleError('same_generation_readiness_mismatch')
        return dict(reply, image_sha256=before['sha256'], boot_id=before['boot_id'])


def run_lifecycle(host, action, expected_sha):
    """Small state machine; tests substitute the host, never production verdicts."""
    if (action not in ACTIONS or type(expected_sha) is not str
            or _RELEASE_RE.fullmatch(expected_sha) is None):
        raise PaidLifecycleError('arguments_invalid')
    effect = False
    fence_released_cleanly = []
    stage = 'preflight'
    try:
        with host.qualified_interval(expected_sha) as snapshot:
            initial = host.registration()
            override = host.override()
            if action == 'status':
                if initial['state'] == 'absent':
                    if observed_socket_state() is not None:
                        raise PaidLifecycleError('residual_socket_present')
                    host.require_idle(snapshot)
                    host.recheck(snapshot)
                    if host.registration() != initial or host.override() != override:
                        raise PaidLifecycleError('status_changed')
                    return dict(state='ABSENT', release=expected_sha, effect=False,
                                enabled_override=override,
                                definition_sha256=host.definition_sha,
                                profile_id=PROFILE_ID, bridge_armed=False,
                                capacity_admitted=False)
                if override != 'enabled':
                    raise PaidLifecycleError('status_state_invalid')
                ready = host.readiness(snapshot, initial)
                host.recheck(snapshot)
                if host.registration() != initial or host.override() != override:
                    raise PaidLifecycleError('status_changed')
                return dict(state='READY', release=expected_sha, effect=False,
                            readiness=ready, enabled_override=override,
                            definition_sha256=host.definition_sha,
                            profile_id=PROFILE_ID, bridge_armed=False,
                            capacity_admitted=False)

            if action == 'start':
                # enabled+absent, registered or running are never adopted or retried.
                if initial['state'] != 'absent':
                    raise PaidLifecycleError('start_requires_unloaded_unregistered')
                if override not in {'disabled', 'default'}:
                    raise PaidLifecycleError('start_requires_unloaded_unenabled')
                if observed_socket_state() is not None:
                    raise PaidLifecycleError('start_socket_occupied')
                host.require_idle(snapshot)
                host.recheck(snapshot)
                if host.registration() != initial or host.override() != override:
                    raise PaidLifecycleError('preimage_changed')
                host.require_incumbent_absent()
                stage = 'enable'
                effect = True
                host.modify('enable')
                if host.override() != 'enabled' or host.registration()['state'] != 'absent':
                    raise PaidLifecycleError('enable_unconfirmed')
                stage = 'bootstrap'
                host.modify('bootstrap')
                loaded = host.registration()
                if loaded['state'] not in {'registered', 'running'}:
                    raise PaidLifecycleError('bootstrap_unconfirmed')
                if loaded['state'] != 'running':
                    stage = 'kickstart'
                    host.modify('kickstart')
                stage = 'readiness'
                for attempt in range(31):
                    current = host.registration()
                    if current['state'] == 'running':
                        ready = host.readiness(snapshot, current)
                        host.recheck(snapshot)
                        if host.registration() != current or host.override() != 'enabled':
                            raise PaidLifecycleError('ready_generation_changed')
                        return dict(state='RUNNING_DISARMED', release=expected_sha,
                                    readiness=ready, effect=True, service_started=True,
                                    admitted=False, armed=False,
                                    enabled_override='enabled',
                                    definition_sha256=host.definition_sha)
                    if current['state'] != 'registered':
                        raise PaidLifecycleError('startup_registration_lost')
                    if attempt < 30:
                        host.pause()
                raise PaidLifecycleError('readiness_deadline')

            if initial['state'] != 'running' or override != 'enabled':
                raise PaidLifecycleError('stop_requires_enabled_running_original')
            before = host.readiness(snapshot, initial)
            host.recheck(snapshot)
            if (host.registration() != initial or host.override() != override
                    or host.readiness(snapshot, initial) != before):
                raise PaidLifecycleError('stop_generation_changed')
            stage = 'quiesce_acquire'
            # A helper denial before any fence exists is a clean refusal; once
            # the transport has answered, quiescence may already be held and
            # every later failure is EFFECT_UNKNOWN with the fence retained.
            acquired = _quiesce_paid_service('acquire', expected_sha,
                                             host.definition_sha)
            effect = True
            fence_reply = _validate_quiescence_receipt(acquired, expected_sha,
                                                       host.definition_sha)
            fence = fence_reply['fence_id']
            if (fence_reply['process'] != before['process']
                    or any(fence_reply['kernel_peer'][key] != before['kernel_peer'][key]
                           for key in before['kernel_peer'])
                    or fence_reply['kernel_peer']['boot_id'] != before['process']['boot_id']):
                raise PaidLifecycleError('quiesce_original_process_changed')
            stage = 'quiesce_hold'
            # Refusals here are provably before any launchctl write: the fence
            # may be released with the same intent; a failed or ambiguous
            # release retains the fence and reports EFFECT_UNKNOWN.
            try:
                host.recheck(snapshot)
                if host.registration() != initial or host.override() != 'enabled':
                    raise PaidLifecycleError('stop_generation_changed')
                if observed_socket_state() is None:
                    raise PaidLifecycleError('stop_socket_absent')
            except PaidLifecycleError as exc:
                if _release_own_fence(fence_reply, expected_sha, host.definition_sha):
                    fence_released_cleanly.append(fence)
                    raise
                raise PaidLifecycleError('quiesce_fence_retained',
                                         effect_unknown=True) from None
            stage = 'disable'
            host.modify('disable')
            if host.override() != 'disabled' or host.registration() != initial:
                raise PaidLifecycleError('disable_unconfirmed')
            stage = 'revalidate'
            revalidated = _validate_quiescence_receipt(
                _quiesce_paid_service('revalidate', expected_sha, host.definition_sha,
                                      fence=fence),
                expected_sha, host.definition_sha)
            if any(revalidated[key] != fence_reply[key] for key in (
                    'fence_id', 'stop_intent', 'broker_process', 'receipt_sha256',
                    'process', 'kernel_peer')):
                raise PaidLifecycleError('quiesce_generation_changed')
            host.require_idle(snapshot)
            host.recheck(snapshot)
            stage = 'bootout'
            host.modify('bootout')
            stage = 'absence'
            for attempt in range(31):
                current = host.registration()
                if current['state'] == 'absent':
                    host.require_idle(snapshot)
                    host.recheck(snapshot)
                    if host.registration() != current or host.override() != 'disabled':
                        raise PaidLifecycleError('absence_changed')
                    if observed_socket_state() is not None:
                        raise PaidLifecycleError('residual_socket_remains')
                    return dict(state='ABSENT', release=expected_sha, effect=True,
                                enabled_override='disabled', quiescence_fence_id=fence,
                                prior_readiness=before,
                                definition_sha256=host.definition_sha)
                if current != initial:
                    raise PaidLifecycleError('stop_generation_changed')
                if attempt < 30:
                    host.pause()
            raise PaidLifecycleError('absence_deadline')
    except Exception as exc:
        code = exc.code if isinstance(exc, PaidLifecycleError) else 'qualification_unavailable'
        unknown = (not isinstance(exc, PaidLifecycleError)) or exc.effect_unknown
        if not unknown and not fence_released_cleanly:
            unknown = effect
        raise PaidLifecycleError(stage + ':' + code, effect_unknown=unknown) from None


def run_paid_lifecycle(action, expected_release_sha, expected_definition_sha256):
    """Public closed entry: exact start|stop|status plus two exact digests.

    start and stop require the parent's real privileged-broker owner gate at
    entry; without that actual broker context they refuse and never fall back
    to any caller-supplied proof. status performs genuinely read-only work.
    """
    if action not in ACTIONS:
        raise PaidLifecycleError('arguments_invalid')
    _release(expected_release_sha)
    _digest256(expected_definition_sha256)
    if sys.platform != 'darwin':
        raise PaidLifecycleError('darwin_required')
    if os.geteuid() != 0:
        raise PaidLifecycleError('root_privilege_required')
    if action in {'start', 'stop'}:
        _require_paid_lifecycle_owner(action, expected_release_sha,
                                      expected_definition_sha256)
    return run_lifecycle(ProductionHost(expected_definition_sha256), action,
                         expected_release_sha)


def main(argv=None):
    """One private Control probe; root lifecycle uses the same-process API."""
    args = sys.argv[1:] if argv is None else argv
    try:
        if (len(args) != 5 or not sys.flags.isolated or not sys.flags.no_site
                or not sys.dont_write_bytecode or args[0] != PROBE_VERB
                or args[1] != '--expected-sha'
                or args[3] != '--expected-manifest-sha256'):
            raise PaidLifecycleError('fixed_installed_arguments_required')
        expected_release, manifest_digest = _release(args[2]), _digest256(args[4])
        if os.geteuid() != CONTROL_UID:
            raise PaidLifecycleError('wrong_caller_principal')
        verify_release_before_import(expected_release, manifest_digest)
        value = probe_paid_socket()
        print(json.dumps(value, sort_keys=True, separators=(',', ':')))
        return 0
    except Exception as exc:
        unknown = isinstance(exc, PaidLifecycleError) and exc.effect_unknown
        print(json.dumps(dict(status='EFFECT_UNKNOWN' if unknown else 'REFUSED',
                              code=exc.code if isinstance(exc, PaidLifecycleError)
                              else 'qualification_unavailable'),
                         sort_keys=True, separators=(',', ':')))
        return 75 if unknown else 65


if __name__ == '__main__':
    raise SystemExit(main())
