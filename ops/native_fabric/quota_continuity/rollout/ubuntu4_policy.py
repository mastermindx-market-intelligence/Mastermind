"""Fixed Ubuntu4 policy/custody maintenance in the existing Fabric support owner.

Planning does not dispatch. Inspection never writes. Installation is ABSENT-only,
requires a separately observed preimage and explicit original-lease settlement,
and never launches work, promotes a mode, clears a lease, or overwrites policy.
A separate fixed ORCH administrative action can clear only group-write under
its own one-shot/physical/live-Broker fences; it is never called by inspection.
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



_CUSTODY_COMPONENTS = frozenset({
    'HOME', 'LANES', 'EXT', 'ACTIVE', 'STATE', 'ORCH', 'POLICY_DIRECTORY',
    'POLICY_FILE', 'PRIOR_INSTALL_RECORD',
})


def _custody_call(component, operation, *args):
    """Label the original first failure; never perform another observation."""
    try:
        return operation(*args)
    except storage.InstallHeld as exc:
        if (type(exc) is storage.InstallHeld and exc.args == ('owner_or_mode',)
                and type(component) is str and component in _CUSTODY_COMPONENTS
                and getattr(exc, '_custody_component', None) is None):
            exc._custody_component = component
        raise


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
    components = dict(zip(paths, ('HOME', 'LANES', 'EXT', 'ACTIVE', 'STATE', 'ORCH', 'POLICY_DIRECTORY')))
    held = []
    lock = None
    staged = None
    record_created = False
    try:
        for path in paths:
            fd = _custody_call(components[path], storage._directory, path, uid)
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
            raw = _custody_call('POLICY_FILE', storage._read, target, 'pools.yaml', uid)
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
                reopened = _custody_call(components[path], storage._directory, path, uid)
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
        prior = _custody_call('PRIOR_INSTALL_RECORD', storage._read, state, RECORD, uid)
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



def inspect_custody(*, home=None, uid=None, platform=None, account=None, hostname=None):
    """Distinct fixed metadata action. Never open policy or prior receipt bodies.

    Caller still needs the SAME live broker guard and separately admitted action.
    No policy preimage, install eligibility or historical facts are supplied.
    """
    home, uid = _scope(home, uid, platform, account, hostname)
    paths = [(home, 'HOME'), (home/'lanes', 'LANES'),
             (home/'lanes/ext', 'EXT'), (home/'lanes/ext/active', 'ACTIVE'),
             (home/'lanes/ext/state', 'STATE'), (home/'lanes/orch', 'ORCH'),
             (home/'lanes/orch/fabric', 'POLICY_DIRECTORY')]
    held, files, result = [], [], []
    lock = None
    try:
        for path, component in paths:
            fd = _custody_call(component, storage._directory, path, uid)
            held.append((path, component, fd, os.fstat(fd)))
            result.append(dict(component=component, state='QUALIFIED',
                               owner_matches=True, group_writable=False, other_writable=False))
        active, state, target = held[3][2], held[4][2], held[6][2]
        lock = os.open('.admission.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                       dir_fd=active)
        lock_stat = os.fstat(lock)
        if (not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != uid
                or lock_stat.st_nlink != 1 or stat.S_IMODE(lock_stat.st_mode) != 0o600):
            raise storage.InstallHeld('admission_lock_identity')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise storage.InstallHeld('admission_lock_busy') from None

        def namespace_current():
            for path, component, fd, original in held:
                reopened = _custody_call(component, storage._directory, path, uid)
                try:
                    if ((os.fstat(reopened).st_dev, os.fstat(reopened).st_ino)
                            != (original.st_dev, original.st_ino)
                            or (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
                            != (original.st_dev, original.st_ino)):
                        raise storage.InstallHeld('directory_changed')
                finally:
                    os.close(reopened)
            if (storage._identity(os.fstat(lock)) != storage._identity(lock_stat)
                    or storage._identity(os.stat('.admission.lock', dir_fd=active, follow_symlinks=False)) != storage._identity(lock_stat)):
                raise storage.InstallHeld('admission_lock_changed')
            if _entries(active) != {'.admission.lock'}:
                raise storage.InstallHeld('active_or_unknown_marker')

        def current():
            namespace_current()
            for fd, name, component, original in files:
                try:
                    now = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    now = None
                if (None if now is None else storage._identity(now)) != original:
                    raise storage.InstallHeld('file_changed')
            # Fixed-file stats may block or run across a namespace change.
            # Rejoin OUR held directories/lock and active set before publishing.
            namespace_current()

        current()
        for fd, name, component in [(target, 'pools.yaml', 'POLICY_FILE'),
                                    (state, RECORD, 'PRIOR_INSTALL_RECORD')]:
            # lstat-equivalent only: no content descriptor, read, digest or parse.
            try:
                item = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                files.append((fd, name, component, None))
                result.append(dict(component=component, state='ABSENT'))
                continue
            _custody_call(component, storage._owned, item, uid)
            if (not stat.S_ISREG(item.st_mode) or item.st_nlink != 1
                    or item.st_size > storage.LIMIT):
                raise storage.InstallHeld('file_identity')
            files.append((fd, name, component, storage._identity(item)))
            result.append(dict(component=component, state='QUALIFIED',
                               owner_matches=True, group_writable=False, other_writable=False))
        current()
        return dict(schema='mastermind.ubuntu4_custody.v1', kind='inspect-custody',
                    components=result, maintenance_authorized=False, replay=False)
    finally:
        if lock is not None:
            os.close(lock)
        for _, _, fd, _ in reversed(held):
            os.close(fd)



# One fixed administrative action in this owner, not a policy/worker lifecycle.
ORCH_REPAIR_ROOT = '01a15741-5e68-7803-8eb4-ccac74a6c04b'
ORCH_REPAIR_RECORD = 'ubuntu4-orch-group-write-repair.intent.json'
ORCH_REPAIR_OUTCOME = 'ubuntu4-orch-group-write-repair.verified.json'


def repair_orch_group_write(*, operation_id, home=None, uid=None, platform=None,
                            account=None, hostname=None):
    """Clear only ORCH group-write, under the existing physical owner fence.

    The local caller MUST retain the same live original Broker guard around the
    transport. No policy/old receipt/descendant is opened or read here. Python
    scope overrides exist only for hermetic tests; the closed transport has none.
    """
    home, uid = _scope(home, uid, platform, account, hostname)
    if (type(operation_id) is not str or not 1 <= len(operation_id) <= 128
            or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-'
                   for c in operation_id)):
        raise storage.InstallHeld('orch_repair_identity')
    held, lock, orch = [], None, None
    attempted = False
    try:
        paths = [home, home/'lanes', home/'lanes/ext', home/'lanes/ext/active',
                 home/'lanes/ext/state']
        for path in paths:
            fd = storage._directory(path, uid)
            held.append((path, fd, os.fstat(fd)))
        lanes, active, state = held[1][1], held[3][1], held[4][1]
        lock = os.open('.admission.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                       dir_fd=active)
        lock_stat = os.fstat(lock)
        if (not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != uid
                or lock_stat.st_nlink != 1 or stat.S_IMODE(lock_stat.st_mode) != 0o600):
            raise storage.InstallHeld('admission_lock_identity')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise storage.InstallHeld('admission_lock_busy') from None

        def directories_current():
            for path, fd, before in held:
                reopened = storage._directory(path, uid)
                try:
                    for item in (os.fstat(reopened), os.fstat(fd)):
                        if ((item.st_dev, item.st_ino, item.st_uid, item.st_gid, item.st_mode)
                                != (before.st_dev, before.st_ino, before.st_uid,
                                    before.st_gid, before.st_mode)):
                            raise storage.InstallHeld('directory_changed')
                finally:
                    os.close(reopened)
            if (storage._identity(os.fstat(lock)) != storage._identity(lock_stat)
                    or storage._identity(os.stat('.admission.lock', dir_fd=active,
                                                follow_symlinks=False)) != storage._identity(lock_stat)):
                raise storage.InstallHeld('admission_lock_changed')
            if _entries(active) != {'.admission.lock'}:
                raise storage.InstallHeld('active_or_unknown_marker')

        directories_current()
        # The ONE scoped exception is opening this fixed leaf before _owned's
        # mode predicate. Never relax _owned or the original inspectors.
        orch = os.open('orch', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                       dir_fd=lanes)
        before = os.fstat(orch)
        mode = stat.S_IMODE(before.st_mode)
        if (not stat.S_ISDIR(before.st_mode) or before.st_uid != uid
                or before.st_gid != pwd.getpwuid(uid).pw_gid
                or not mode & 0o020 or mode & 0o002):
            raise storage.InstallHeld('orch_repair_preimage')
        def identity(item):
            return (item.st_dev, item.st_ino, item.st_uid, item.st_gid,
                    item.st_mode, item.st_nlink, item.st_size,
                    item.st_mtime_ns, item.st_ctime_ns)
        def no_acl():
            # Names only, no xattr/ACL contents. Unknown/unsupported fails closed.
            list_names = getattr(os, 'listxattr', None)
            if not callable(list_names):
                raise storage.InstallHeld('orch_repair_acl_unknown')
            if any('acl' in name.lower() for name in list_names(orch)):
                raise storage.InstallHeld('orch_repair_acl_unknown')
        def current(expected):
            directories_current()
            no_acl()
            if (identity(os.fstat(orch)) != identity(expected)
                    or identity(os.stat('orch', dir_fd=lanes, follow_symlinks=False))
                    != identity(expected)):
                raise storage.InstallHeld('directory_changed')
            directories_current()
            # Ancestor/lock rejoins can block. Finish with OUR fixed leaf's
            # fresh ACL and full held/named preimage immediately before effect.
            no_acl()
            if (identity(os.fstat(orch)) != identity(expected)
                    or identity(os.stat('orch', dir_fd=lanes, follow_symlinks=False))
                    != identity(expected)):
                raise storage.InstallHeld('directory_changed')
        current(before)
        for name in (ORCH_REPAIR_RECORD, ORCH_REPAIR_OUTCOME):
            try:
                os.stat(name, dir_fd=state, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise storage.InstallHeld('orch_repair_prior_hold')
        current(before)
        after_mode = mode & ~0o020
        receipt = dict(schema='mastermind.ubuntu4_orch_group_write_repair.v1',
                       root=ORCH_REPAIR_ROOT, operation_id=operation_id, state='INTENT',
                       preimage=list(identity(before)), expected_mode=after_mode,
                       replay=False, lifecycle_authority=False)
        # Attempted is sticky even if an exclusive create/fsync only partly succeeds.
        attempted = True
        storage._write_new(state, ORCH_REPAIR_RECORD,
                           json.dumps(receipt, sort_keys=True).encode())
        current(before)
        os.fchmod(orch, after_mode)
        os.fsync(orch)
        after = os.fstat(orch)
        if ((after.st_dev, after.st_ino, after.st_uid, after.st_gid,
             after.st_nlink, after.st_size, after.st_mtime_ns)
                != (before.st_dev, before.st_ino, before.st_uid, before.st_gid,
                    before.st_nlink, before.st_size, before.st_mtime_ns)
                or stat.S_IMODE(after.st_mode) != after_mode):
            raise storage.InstallHeld('orch_repair_postimage')
        current(after)
        storage._write_new(state, ORCH_REPAIR_OUTCOME,
                           json.dumps(dict(receipt, state='VERIFIED',
                                           postimage=list(identity(after))), sort_keys=True).encode())
        current(after)
        return dict(schema=receipt['schema'], root=ORCH_REPAIR_ROOT,
                    operation_id=operation_id, state='VERIFIED',
                    group_write_removed=True, replay=False, lifecycle_authority=False)
    except BaseException as exc:
        if attempted:
            raise storage.InstallHeld('orch_repair_effect_unknown_no_replay') from exc
        raise
    finally:
        if orch is not None:
            os.close(orch)
        if lock is not None:
            os.close(lock)
        for _, fd, _ in reversed(held):
            os.close(fd)


def guarded_orch_repair(driver, registry_bytes, ssh_config_bytes, *, operation_id,
                        expected_module_sha, expected_storage_sha):
    """Root-only composition using the SAME enrolled Broker, not a snapshot.

    The caller source-qualifies its selected native generation/namespace as for
    the existing Root actions and prevents new root dispatch. No Broker instance,
    lock/DB path, caller guard, source loader, grant or retry is created here.
    """
    from lease_broker import Broker
    with Broker.qualification_maintenance_guard(
            orchestrator_id=ORCH_REPAIR_ROOT, pool='minimax', host='ubuntu4') as guard:
        def current():
            value = guard.require_current()
            if (type(value) is not dict
                    or value.get('schema') != 'mastermind.fabric_qualification_quiescence.v1'
                    or value.get('root') != ORCH_REPAIR_ROOT or value.get('pool') != 'minimax'
                    or value.get('host') != 'ubuntu4' or value.get('account_coverage') != 'ALL_ACCOUNTS'
                    or value.get('state') != 'QUIESCENT_IN_SCOPE'
                    or type(value.get('held_lease_count')) is not int or value['held_lease_count'] != 0
                    or type(value.get('pending_waiter_count')) is not int or value['pending_waiter_count'] != 0):
                raise storage.InstallHeld('orch_repair_live_guard')
        current()
        plan = transport_plan(driver, registry_bytes, ssh_config_bytes,
                              kind='repair-orch-group-write', operation_id=operation_id,
                              expected_module_sha=expected_module_sha,
                              expected_storage_sha=expected_storage_sha)
        current()
        result = driver.run(plan['argv'], plan['timeout'])
        current()
    return result


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
            'orch_repair_identity': 'ORCH_REPAIR_IDENTITY',
            'orch_repair_preimage': 'ORCH_REPAIR_PREIMAGE_UNQUALIFIED',
            'orch_repair_acl_unknown': 'ORCH_REPAIR_ACL_UNQUALIFIED',
            'orch_repair_prior_hold': 'ORCH_REPAIR_PRIOR_HOLD',
            'orch_repair_postimage': 'ORCH_REPAIR_POSTIMAGE_UNQUALIFIED',
            'orch_repair_effect_unknown_no_replay': 'ORCH_REPAIR_EFFECT_UNKNOWN',
            'orch_repair_live_guard': 'ORCH_REPAIR_LIVE_GUARD_REQUIRED',
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


def public_refusal(exc):
    """No historical reconstruction or raw UID/path/mode/error disclosure."""
    result = {'reason': public_reason(exc)}
    if type(exc) is not storage.InstallHeld or exc.args != ('owner_or_mode',):
        return result
    component = getattr(exc, '_custody_component', None)
    facts = getattr(exc, '_custody_predicates', None)
    if (type(component) is not str or component not in _CUSTODY_COMPONENTS
            or type(facts) is not tuple or len(facts) != 3
            or any(type(value) is not bool for value in facts)
            or (facts[0] and not facts[1] and not facts[2])):
        return result
    result['custody'] = {'component': component, 'owner_matches': facts[0],
                         'group_writable': facts[1], 'other_writable': facts[2]}
    return result


def transport_plan(driver, registry_bytes, ssh_config_bytes, *, kind,
                   expected_module_sha, expected_storage_sha, payload=None,
                   expected_before=None, operation_id=None, original_settled=False,
                   expected_policy_sha=None):
    """One fixed enrolled transport plan; no network or automatic source trust."""
    binding = storage.enrolled_binding('ubuntu4', registry_bytes, ssh_config_bytes)
    if binding['binding'] != {'account': ACCOUNT, 'hostnames': [HOSTNAME]}:
        raise storage.InstallHeld('fixed_host_account')
    if kind not in {'inspect', 'install', 'inspect-custody', 'repair-orch-group-write'}:
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
    if kind == 'repair-orch-group-write':
        if (payload is not None or expected_before is not None or expected_policy_sha is not None
                or original_settled is not False or type(operation_id) is not str
                or not 1 <= len(operation_id) <= 128
                or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-' for c in operation_id)):
            raise storage.InstallHeld('orch_repair_identity')
        request['operation_id'] = operation_id
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
            'try: print(json.dumps(p["inspect_custody"]() if r["kind"]=="inspect-custody" else p["repair_orch_group_write"](operation_id=r["operation_id"]) if r["kind"]=="repair-orch-group-write" else p["operate"](**r),sort_keys=True))\n'
            'except (OSError,ValueError) as e: print(json.dumps(dict({"state":"HELD_OR_UNKNOWN","replay":False},**p["public_refusal"](e))));raise SystemExit(78)\n')
    command = shlex.join(['python3', '-c', code])
    return {'kind': kind, 'target': binding, 'argv': driver.SSH + [binding['alias'], command],
            'timeout': 20, 'dispatch_authorized': False,
            'remote_preimage': expected_before, 'policy_sha256': _sha(payload) if payload else None}
