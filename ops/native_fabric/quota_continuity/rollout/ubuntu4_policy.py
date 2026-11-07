"""Fixed first-policy enrollment in the existing Fabric support owner.

Planning does not dispatch. Inspection never writes. Installation is ABSENT-only,
requires a separately observed preimage and explicit original-lease settlement,
and never launches work, promotes a mode, clears a lease, or overwrites policy.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shlex
import socket
import stat
import sys
import types
import uuid

if 'storage' not in globals():
    from ops.fleet_storage_cleanup import preview_install as storage

RECORD = 'ubuntu4-routing-policy.first-install.json'
SCHEMA = 'mastermind.ubuntu4_policy_enrollment.v1'
ACCOUNT = 'ubuntu4'
HOSTNAME = 'ubuntu4-MS-7E61'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hex(value):
    return (type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value))


def _scope(home, uid, platform, account, hostname):
    uid = os.getuid() if uid is None else uid
    if home is None:
        # HOME is caller environment, not the enrolled account's target owner.
        home = Path(pwd.getpwuid(uid).pw_dir)
        if home != Path('/home/ubuntu4'):
            raise storage.InstallHeld('fixed_account_home')
    else:
        home = Path(home)  # Local hermetic API only; closed transport exposes no override.
    platform = sys.platform if platform is None else platform
    account = pwd.getpwuid(uid).pw_name if account is None else account
    hostname = socket.gethostname() if hostname is None else hostname
    if platform != 'linux' or account != ACCOUNT or hostname != HOSTNAME or uid == 0:
        raise storage.InstallHeld('fixed_host_account')
    return home, uid


def _entries(fd):
    result = set()
    with os.scandir(fd) as items:
        for item in items:
            if len(result) >= 20000:
                raise storage.InstallHeld('active_history_unknown')
            result.add(item.name)
    return result


def operate(*, kind, payload=None, expected_after=None, expected_before=None,
            operation_id=None, original_settled=False, home=None, uid=None,
            platform=None, account=None, hostname=None):
    if kind not in {'inspect', 'install'}:
        raise storage.InstallHeld('operation_kind')
    home, uid = _scope(home, uid, platform, account, hostname)
    if kind == 'install':
        if (expected_before != 'ABSENT' or original_settled is not True
                or type(operation_id) is not str or not operation_id
                or len(operation_id) > 128
                or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-' for c in operation_id)):
            raise storage.InstallHeld('preimage_or_settlement_required')
        if (type(payload) is not bytes or not 0 < len(payload) <= storage.LIMIT
                or not _hex(expected_after) or _sha(payload) != expected_after):
            raise storage.InstallHeld('policy_source_pin')
    # Every directory must already exist. No broad bootstrap/mkdir or source copy.
    paths = [home, home/'lanes', home/'lanes/ext', home/'lanes/ext/active',
             home/'lanes/ext/state', home/'lanes/orch', home/'lanes/orch/fabric']
    held = []
    lock = None
    staged = None
    record_created = False
    try:
        for path in paths:
            fd = storage._directory(path, uid)
            held.append((path, fd, os.fstat(fd)))
        active, state, target = held[3][1], held[4][1], held[6][1]
        lock = os.open('.admission.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                       dir_fd=active)  # Existing lock only; never replace/create it.
        lock_stat = os.fstat(lock)
        if (not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != uid
                or lock_stat.st_nlink != 1 or stat.S_IMODE(lock_stat.st_mode) != 0o600):
            raise storage.InstallHeld('admission_lock_identity')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise storage.InstallHeld('admission_lock_busy') from None

        policy_identity = [None]

        def policy_snapshot():
            def identity():
                try:
                    return storage._identity(os.stat('pools.yaml', dir_fd=target, follow_symlinks=False))
                except FileNotFoundError:
                    return 'ABSENT'
            before_identity = identity()
            raw = storage._read(target, 'pools.yaml', uid)
            after_identity = identity()
            if before_identity != after_identity:
                raise storage.InstallHeld('policy_changed')
            return raw, after_identity

        def current():
            if policy_identity[0] is not None:
                try:
                    named = storage._identity(os.stat('pools.yaml', dir_fd=target, follow_symlinks=False))
                except FileNotFoundError:
                    named = 'ABSENT'
                if named != policy_identity[0]:
                    raise storage.InstallHeld('policy_changed')
            for path, fd, original in held:
                reopened = storage._directory(path, uid)
                try:
                    named = os.fstat(reopened)
                    now = os.fstat(fd)
                    if ((named.st_dev, named.st_ino) != (original.st_dev, original.st_ino)
                            or (now.st_dev, now.st_ino) != (original.st_dev, original.st_ino)):
                        raise storage.InstallHeld('directory_changed')
                finally:
                    os.close(reopened)
            named = os.stat('.admission.lock', dir_fd=active, follow_symlinks=False)
            if storage._identity(named) != storage._identity(lock_stat):
                raise storage.InstallHeld('admission_lock_changed')
            if _entries(active) != {'.admission.lock'}:
                raise storage.InstallHeld('active_or_unknown_marker')

        current()
        before, policy_identity[0] = policy_snapshot()
        preimage = 'ABSENT' if before is None else _sha(before)
        prior = storage._read(state, RECORD, uid)
        current()
        if kind == 'inspect':
            return {'schema': SCHEMA, 'kind': kind, 'preimage': preimage,
                    'prior_install': prior is not None, 'installation_authorized': False}
        if preimage != expected_before or prior is not None:
            raise storage.InstallHeld('preimage_changed_or_prior_install_hold')
        receipt = {'schema': SCHEMA, 'operation_id': operation_id,
                   'expected_before': 'ABSENT', 'expected_after': expected_after,
                   'original_settled': True, 'state': 'INTENT'}
        # This fixed one-shot history always holds subsequent writes, including
        # VERIFIED. A late fence/receipt failure cannot become replay permission.
        storage._write_new(state, RECORD, json.dumps(receipt, sort_keys=True).encode())
        record_created = True
        current()
        staged = '.ubuntu4-policy-' + uuid.uuid4().hex
        storage._write_new(target, staged, payload)
        current()
        # link is no-clobber even if a non-cooperating actor creates the target.
        os.link(staged, 'pools.yaml', src_dir_fd=target, dst_dir_fd=target,
                follow_symlinks=False)
        os.unlink(staged, dir_fd=target)
        staged = None
        os.fsync(target)
        after, policy_identity[0] = policy_snapshot()
        if after != payload:
            raise storage.InstallHeld('postimage_changed')
        current()
        storage._write_new(state, RECORD + '.verified',
                           json.dumps(dict(receipt, state='VERIFIED'), sort_keys=True).encode())
        current()
        return dict(receipt, state='VERIFIED')
    except BaseException as exc:
        if record_created:
            raise storage.InstallHeld('install_effect_unknown_no_replay') from exc
        raise
    finally:
        if staged is not None:
            # Only this call's own exclusive stage, through its still-held fd.
            try:
                os.unlink(staged, dir_fd=held[6][1])
            except OSError:
                pass
        if lock is not None:
            os.close(lock)
        for _, fd, _ in reversed(held):
            os.close(fd)



def public_reason(exc):
    """Closed diagnostic labels only; never expose exception prose or paths."""
    if type(exc) is storage.InstallHeld and len(exc.args) == 1:
        code = exc.args[0]
        allowed = {
            'fixed_host_account': 'HOST_ACCOUNT_MISMATCH',
            'fixed_account_home': 'ACCOUNT_HOME_MISMATCH',
            'owner_or_mode': 'OWNER_OR_MODE_UNQUALIFIED',
            'directory_identity': 'DIRECTORY_UNQUALIFIED',
            'file_identity': 'FILE_UNQUALIFIED',
            'file_changed': 'FILE_CHANGED',
            'admission_lock_identity': 'ADMISSION_LOCK_UNQUALIFIED',
            'admission_lock_busy': 'ADMISSION_LOCK_BUSY',
            'admission_lock_changed': 'ADMISSION_LOCK_CHANGED',
            'directory_changed': 'DIRECTORY_CHANGED',
            'active_or_unknown_marker': 'ACTIVE_OR_UNKNOWN_MARKER',
            'active_history_unknown': 'ACTIVE_HISTORY_UNKNOWN',
            'policy_changed': 'POLICY_CHANGED',
            'preimage_changed_or_prior_install_hold': 'PREIMAGE_OR_PRIOR_INSTALL_HOLD',
            'install_effect_unknown_no_replay': 'INSTALL_EFFECT_UNKNOWN',
        }
        if type(code) is str:
            return allowed.get(code, 'UNCLASSIFIED')
    if type(exc) in {OSError, FileNotFoundError, NotADirectoryError, PermissionError,
                     FileExistsError, BlockingIOError}:
        import errno
        return {errno.ENOENT: 'REQUIRED_PATH_ABSENT', errno.ENOTDIR: 'DIRECTORY_UNQUALIFIED',
                errno.ELOOP: 'SYMLINK_REFUSED', errno.EACCES: 'OS_ACCESS_REFUSED',
                errno.EPERM: 'OS_ACCESS_REFUSED', errno.EEXIST: 'TARGET_ALREADY_EXISTS',
                errno.EBUSY: 'OWNER_BUSY', errno.EAGAIN: 'OWNER_BUSY'}.get(exc.errno, 'OS_ERROR_UNCLASSIFIED')
    return 'UNCLASSIFIED'

def transport_plan(driver, registry_bytes, ssh_config_bytes, *, kind,
                   expected_module_sha, expected_storage_sha, payload=None,
                   expected_before=None, operation_id=None, original_settled=False,
                   expected_policy_sha=None):
    """One fixed enrolled transport plan; no network or automatic source trust."""
    binding = storage.enrolled_binding('ubuntu4', registry_bytes, ssh_config_bytes)
    if binding['binding'] != {'account': ACCOUNT, 'hostnames': [HOSTNAME]}:
        raise storage.InstallHeld('fixed_host_account')
    if kind not in {'inspect', 'install'}:
        raise storage.InstallHeld('operation_kind')
    if not _hex(expected_module_sha) or not _hex(expected_storage_sha):
        raise storage.InstallHeld('installer_source_pin')
    sources = []
    for file, wanted in [(Path(storage.__file__), expected_storage_sha),
                         (Path(__file__), expected_module_sha)]:
        fd = storage._directory(file.parent, os.getuid())
        try:
            raw = storage._read(fd, file.name, os.getuid())
        finally:
            os.close(fd)
        if raw is None or _sha(raw) != wanted:
            raise storage.InstallHeld('installer_source_pin')
        sources.append((base64.b64encode(raw).decode(), wanted))
    request = {'kind': kind}
    if kind == 'install':
        if (type(payload) is not bytes or not 0 < len(payload) <= storage.LIMIT
                or expected_before != 'ABSENT' or original_settled is not True
                or not operation_id or not _hex(expected_policy_sha)
                or _sha(payload) != expected_policy_sha):
            raise storage.InstallHeld('preimage_or_settlement_required')
        request.update(payload=base64.b64encode(payload).decode(),
                       expected_before=expected_before, expected_after=expected_policy_sha,
                       operation_id=operation_id, original_settled=True)
    code = ('import base64,hashlib,json,types\n'
            'sources=' + repr(sources) + '\n'
            'n={"__name__":"fixed_storage_dependency","__file__":"preview_install.py"}\n'
            'raw=base64.b64decode(sources[0][0])\n'
            'if hashlib.sha256(raw).hexdigest()!=sources[0][1]:raise SystemExit(78)\n'
            'exec(compile(raw,"preview_install.py","exec"),n)\n'
            'p={"__name__":"fixed_policy_enrollment","__file__":"ubuntu4_policy.py","storage":types.SimpleNamespace(**n)}\n'
            'raw=base64.b64decode(sources[1][0])\n'
            'if hashlib.sha256(raw).hexdigest()!=sources[1][1]:raise SystemExit(78)\n'
            'exec(compile(raw,"ubuntu4_policy.py","exec"),p)\n'
            'r=json.loads(' + repr(json.dumps(request)) + ')\n'
            'if "payload" in r:r["payload"]=base64.b64decode(r["payload"])\n'
            'try: print(json.dumps(p["operate"](**r),sort_keys=True))\n'
            'except (OSError,ValueError) as e: print(json.dumps({"state":"HELD_OR_UNKNOWN","replay":False,"reason":p["public_reason"](e)}));raise SystemExit(78)\n')
    command = shlex.join(['python3', '-c', code])
    return {'kind': kind, 'target': binding, 'argv': driver.SSH + [binding['alias'], command],
            'timeout': 20, 'dispatch_authorized': False,
            'remote_preimage': expected_before, 'policy_sha256': _sha(payload) if payload else None}
