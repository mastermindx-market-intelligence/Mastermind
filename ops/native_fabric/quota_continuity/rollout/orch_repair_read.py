"""Fixed original ORCH repair read in the incumbent Ubuntu4 maintenance owner.

No command-line entry, writes, policy read, Broker/lease acquisition or replay.
Transport compiles these exact hash-bound bytes with the existing storage owner.
"""
import fcntl
import json
import os
import pwd
import stat
import hashlib
from pathlib import Path

if 'storage' not in globals():
    from ops.fleet_storage_cleanup import preview_install as storage

ORCH_REPAIR_ROOT = '01a15741-5e68-7803-8eb4-ccac74a6c04b'
ORCH_REPAIR_RECORD = 'ubuntu4-orch-group-write-repair.intent.json'
ORCH_REPAIR_OUTCOME = 'ubuntu4-orch-group-write-repair.verified.json'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


if '_scope' not in globals():
    from ops.native_fabric.quota_continuity.rollout.ubuntu4_policy import _scope, _entries


# This is the original operation, not a new maintenance identity or retry token.
ORCH_REPAIR_ORIGINAL_OPERATION = 'mmos-u4-orch-maintenance-01a15741-20261108-v1'


def read_orch_repair(*, operation_id, home=None, uid=None, platform=None,
                     account=None, hostname=None):
    """Read ONLY the original fixed repair receipts, with current physical custody.

    No Broker acquisition, policy/old enrollment read, write, chmod or repair call.
    Missing/partial records never prove that an effect did not occur. Scope
    overrides are hermetic-test inputs and are absent from the closed transport.
    """
    home, uid = _scope(home, uid, platform, account, hostname)
    if type(operation_id) is not str or operation_id != ORCH_REPAIR_ORIGINAL_OPERATION:
        raise storage.InstallHeld('orch_repair_identity')
    held, lock, orch = [], None, None
    try:
        for path in [home, home/'lanes', home/'lanes/ext', home/'lanes/ext/active',
                     home/'lanes/ext/state']:
            fd = storage._directory(path, uid)
            held.append((path, fd, os.fstat(fd)))
        lanes, active, state = held[1][1], held[3][1], held[4][1]
        lock = os.open('.admission.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                       dir_fd=active)
        lock_stat = os.fstat(lock)
        if (not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != uid
                or lock_stat.st_nlink != 1 or stat.S_IMODE(lock_stat.st_mode) != 0o600):
            raise storage.InstallHeld('admission_lock_identity')
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
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
        orch = os.open('orch', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=lanes)
        before = os.fstat(orch)
        if (not stat.S_ISDIR(before.st_mode) or before.st_uid != uid
                or before.st_gid != pwd.getpwuid(uid).pw_gid or before.st_mode & 0o002):
            raise storage.InstallHeld('orch_repair_preimage')

        def identity(s):
            return [s.st_dev, s.st_ino, s.st_uid, s.st_gid, s.st_mode,
                    s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns]

        snapshots = {}
        def read_fixed(name):
            try:
                s = os.stat(name, dir_fd=state, follow_symlinks=False)
            except FileNotFoundError:
                snapshots[name] = None
                return None
            if (not stat.S_ISREG(s.st_mode) or s.st_uid != uid or s.st_nlink != 1
                    or stat.S_IMODE(s.st_mode) != 0o600):
                raise storage.InstallHeld('orch_repair_record_unqualified')
            raw = storage._read(state, name, uid)
            if (raw is None or storage._identity(os.stat(name, dir_fd=state,
                       follow_symlinks=False)) != storage._identity(s)):
                raise storage.InstallHeld('orch_repair_record_changed')
            snapshots[name] = storage._identity(s)
            return raw

        intent_raw = read_fixed(ORCH_REPAIR_RECORD)
        outcome_raw = read_fixed(ORCH_REPAIR_OUTCOME)
        result = dict(schema='mastermind.ubuntu4_orch_repair_read.v1',
                      root=ORCH_REPAIR_ROOT, operation_id=operation_id, state='UNKNOWN',
                      reason='ORIGINAL_RECORDS_ABSENT', current_postimage_qualified=False,
                      current_reason='ORIGINAL_COMPLETION_UNKNOWN', replay=False,
                      retry_authorized=False, lifecycle_authority=False)

        def closed_json(raw, keys):
            def pairs(items):
                value = {}
                for key, item in items:
                    if key in value:
                        raise storage.InstallHeld('orch_repair_record_unqualified')
                    value[key] = item
                return value
            try:
                value = json.loads(raw, object_pairs_hook=pairs)
            except (ValueError, UnicodeError, RecursionError):
                raise storage.InstallHeld('orch_repair_record_unqualified') from None
            if type(value) is not dict or set(value) != keys:
                raise storage.InstallHeld('orch_repair_record_unqualified')
            return value

        keys = {'schema', 'root', 'operation_id', 'state', 'preimage', 'expected_mode',
                'replay', 'lifecycle_authority'}
        if intent_raw is None and outcome_raw is not None:
            raise storage.InstallHeld('orch_repair_record_unqualified')
        if intent_raw is not None:
            intent = closed_json(intent_raw, keys)
            pre = intent['preimage']
            if (intent['schema'] != 'mastermind.ubuntu4_orch_group_write_repair.v1'
                    or intent['root'] != ORCH_REPAIR_ROOT or intent['operation_id'] != operation_id
                    or intent['state'] != 'INTENT' or intent['replay'] is not False
                    or intent['lifecycle_authority'] is not False
                    or type(pre) is not list or len(pre) != 9
                    or any(type(n) is not int or n < 0 for n in pre)
                    or not stat.S_ISDIR(pre[4]) or pre[2] != uid
                    or pre[3] != pwd.getpwuid(uid).pw_gid
                    or not pre[4] & 0o020 or pre[4] & 0o002
                    or type(intent['expected_mode']) is not int
                    or intent['expected_mode'] != (stat.S_IMODE(pre[4]) & ~0o020)):
                raise storage.InstallHeld('orch_repair_record_unqualified')
            result['reason'] = 'ORIGINAL_INTENT_ONLY'
            if outcome_raw is not None:
                outcome = closed_json(outcome_raw, keys | {'postimage'})
                post = outcome['postimage']
                if (json.dumps(outcome, sort_keys=True) != json.dumps(dict(intent, state='VERIFIED', postimage=post), sort_keys=True)
                        or type(post) is not list or len(post) != 9
                        or any(type(n) is not int or n < 0 for n in post)
                        or any(post[i] != pre[i] for i in (0, 1, 2, 3, 5, 6, 7))
                        or post[4] != pre[4] & ~0o020):
                    raise storage.InstallHeld('orch_repair_record_unqualified')
                result.update(state='VERIFIED', reason='ORIGINAL_RECEIPTS_VERIFIED',
                              current_postimage_qualified=identity(before) == post,
                              current_reason=('RECORDED_POSTIMAGE_CURRENT' if identity(before) == post
                                              else 'RECORDED_POSTIMAGE_CHANGED'),
                              intent_sha256=_sha(intent_raw), verified_sha256=_sha(outcome_raw))

        # All body reads precede final ancestor/lock/receipt/ACL/leaf joins.
        # Absence or INTENT-only stays UNKNOWN even if the observed mode is 0755.
        directories_current()
        for name, expected in snapshots.items():
            try:
                s = os.stat(name, dir_fd=state, follow_symlinks=False)
            except FileNotFoundError:
                if expected is not None:
                    raise storage.InstallHeld('orch_repair_record_changed')
            else:
                if expected is None or storage._identity(s) != expected:
                    raise storage.InstallHeld('orch_repair_record_changed')
        names = getattr(os, 'listxattr', None)
        try:
            acl_qualified = callable(names) and not any('acl' in name.lower() for name in names(orch))
        except OSError:
            acl_qualified = False
        if not acl_qualified:
            result['current_postimage_qualified'] = False
            result['current_reason'] = 'CURRENT_ACL_UNQUALIFIED'
        if (identity(os.fstat(orch)) != identity(before)
                or identity(os.stat('orch', dir_fd=lanes, follow_symlinks=False)) != identity(before)):
            raise storage.InstallHeld('directory_changed')
        return result
    finally:
        if orch is not None:
            os.close(orch)
        if lock is not None:
            os.close(lock)
        for _, fd, _ in reversed(held):
            os.close(fd)


# Prospective opt-in framing. This is observation data, never an action grant.
FRAME_LIMIT = 4096
FRAME_SCHEMA = 'mastermind.orch_original_read_frame.v1'
CONTEXT_SCHEMA = 'mastermind.orch_original_read_context.v1'
FIXED_SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20',
             '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=4']


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def framed_plan(driver, binding, sources, expected_driver_sha):
    """Literal same-owner plan; no caller command/path, authority or dispatch."""
    import base64
    import shlex
    file = Path(storage.__file__).with_name('fleet_remote_sweep.py')
    fd = storage._directory(file.parent, os.getuid())
    try:
        raw = storage._read(fd, file.name, os.getuid())
    finally:
        os.close(fd)
    if (type(expected_driver_sha) is not str or len(expected_driver_sha) != 64
            or raw is None or _sha(raw) != expected_driver_sha or driver.SSH != FIXED_SSH):
        raise storage.InstallHeld('installer_source_pin')
    context = dict(schema=CONTEXT_SCHEMA, root=ORCH_REPAIR_ROOT,
                   operation_id=ORCH_REPAIR_ORIGINAL_OPERATION,
                   target_sha256=_sha(_canonical(binding)),
                   sources=dict(storage=sources[0][1], module=sources[1][1],
                                reader=sources[2][1], driver=expected_driver_sha))
    code = ('import base64,hashlib,json,types\nsources=' + repr(sources) + '\n'
            'n={"__name__":"fixed_storage_dependency","__file__":"preview_install.py"}\n'
            'p={"__name__":"fixed_policy_enrollment","__file__":"ubuntu4_policy.py"}\n'
            'q={"__name__":"fixed_orch_repair_read"}\n'
            'for index,namespace in enumerate((n,p,q)):\n'
            ' raw=base64.b64decode(sources[index][0])\n'
            ' if hashlib.sha256(raw).hexdigest()!=sources[index][1]:raise SystemExit(78)\n'
            ' if index:namespace["storage"]=types.SimpleNamespace(**n)\n'
            ' if index==2:namespace.update(_scope=p["_scope"],_entries=p["_entries"],_public_refusal=p["public_refusal"])\n'
            ' exec(compile(raw,("preview_install.py","ubuntu4_policy.py","orch_repair_read.py")[index],"exec"),namespace)\n'
            'q["stream_original_read"](json.loads(' + repr(_canonical(context).decode()) + '))\n')
    argv = list(FIXED_SSH)
    argv[argv.index('ConnectTimeout=20')] = 'ConnectTimeout=10'
    return dict(kind='read-orch-repair-framed', target=binding, context=context,
                argv=argv + [binding['alias'], shlex.join(['python3', '-c', code])],
                timeout=20, connect_timeout=10, dispatch_authorized=False)


def _valid_context(value):
    keys = {'schema', 'root', 'operation_id', 'target_sha256', 'sources'}
    return (type(value) is dict and set(value) == keys
            and value['schema'] == CONTEXT_SCHEMA and value['root'] == ORCH_REPAIR_ROOT
            and value['operation_id'] == ORCH_REPAIR_ORIGINAL_OPERATION
            and type(value['sources']) is dict
            and set(value['sources']) == {'storage', 'module', 'reader', 'driver'}
            and all(type(s) is str and len(s) == 64 and all(c in '0123456789abcdef' for c in s)
                    for s in [value['target_sha256'], *value['sources'].values()]))


def stream_original_read(context):
    """Frames follow exact fixed-account scope check; no raw exception output."""
    if not _valid_context(context):
        raise storage.InstallHeld('orch_repair_identity')
    def emit(kind, result=None):
        frame = dict(schema=FRAME_SCHEMA, context=context, kind=kind, result=result)
        raw = _canonical(frame) + b'\n'
        if len(raw) > FRAME_LIMIT // 2:
            raise storage.InstallHeld('orch_repair_record_unqualified')
        print(raw.decode(), end='', flush=True)
    if '_public_refusal' in globals():
        refusal = _public_refusal
    else:
        from ops.native_fabric.quota_continuity.rollout.ubuntu4_policy import public_refusal as refusal
    try:
        _scope(None, None, None, None, None)
    except (OSError, ValueError) as exc:
        emit('SCOPE_REFUSED', dict(state='HELD_OR_UNKNOWN', replay=False,
             retry_authorized=False, lifecycle_authority=False, **refusal(exc)))
        return
    emit('READ_ENTERED')
    try:
        value = read_orch_repair(operation_id=ORCH_REPAIR_ORIGINAL_OPERATION)
    except (OSError, ValueError) as exc:
        value = dict(state='HELD_OR_UNKNOWN', replay=False, retry_authorized=False,
                     lifecycle_authority=False, **refusal(exc))
    emit('RESULT', value)


PUBLIC_READ_REASONS = frozenset({
    'HOST_ACCOUNT_MISMATCH', 'ACCOUNT_HOME_MISMATCH', 'OWNER_OR_MODE_UNQUALIFIED',
    'DIRECTORY_UNQUALIFIED', 'FILE_UNQUALIFIED', 'FILE_CHANGED', 'ADMISSION_LOCK_UNQUALIFIED',
    'ADMISSION_LOCK_BUSY', 'ADMISSION_LOCK_CHANGED', 'DIRECTORY_CHANGED',
    'ACTIVE_OR_UNKNOWN_MARKER', 'ACTIVE_HISTORY_UNKNOWN', 'ORCH_REPAIR_IDENTITY',
    'ORCH_REPAIR_PREIMAGE_UNQUALIFIED', 'ORCH_REPAIR_ACL_UNQUALIFIED',
    'ORCH_REPAIR_RECORD_UNQUALIFIED', 'ORCH_REPAIR_RECORD_CHANGED',
    'REQUIRED_PATH_ABSENT', 'SYMLINK_REFUSED', 'OS_ACCESS_REFUSED', 'TARGET_ALREADY_EXISTS',
    'OWNER_BUSY', 'OS_ERROR_UNCLASSIFIED', 'UNCLASSIFIED',
})


def _qualified_result(value):
    """Only core closed read fields survive; arbitrary error text never escapes."""
    if type(value) is not dict:
        return None
    if value.get('state') == 'HELD_OR_UNKNOWN':
        if (set(value) != {'state', 'replay', 'retry_authorized', 'lifecycle_authority', 'reason'}
                or type(value.get('reason')) is not str or value['reason'] not in PUBLIC_READ_REASONS
                or value.get('replay') is not False or value.get('retry_authorized') is not False
                or value.get('lifecycle_authority') is not False):
            return None
        # Preserve no source exception text or attacker-chosen error strings.
        return dict(state='HELD_OR_UNKNOWN', reason=value['reason'], replay=False,
                    retry_authorized=False, lifecycle_authority=False)
    keys = {'schema', 'root', 'operation_id', 'state', 'reason', 'current_postimage_qualified',
            'current_reason', 'replay', 'retry_authorized', 'lifecycle_authority'}
    verified = value.get('state') == 'VERIFIED'
    if (set(value) != keys | ({'intent_sha256', 'verified_sha256'} if verified else set())
            or value.get('schema') != 'mastermind.ubuntu4_orch_repair_read.v1'
            or value.get('root') != ORCH_REPAIR_ROOT
            or value.get('operation_id') != ORCH_REPAIR_ORIGINAL_OPERATION
            or any(value.get(k) is not False for k in ['replay','retry_authorized','lifecycle_authority'])
            or type(value.get('current_postimage_qualified')) is not bool):
        return None
    if verified:
        if (value['reason'] != 'ORIGINAL_RECEIPTS_VERIFIED'
                or value['current_reason'] not in {'RECORDED_POSTIMAGE_CURRENT','RECORDED_POSTIMAGE_CHANGED','CURRENT_ACL_UNQUALIFIED'}
                or value['current_postimage_qualified'] != (value['current_reason']=='RECORDED_POSTIMAGE_CURRENT')
                or any(type(value[k]) is not str or len(value[k]) != 64
                       or any(c not in '0123456789abcdef' for c in value[k])
                       for k in ['intent_sha256','verified_sha256'])):
            return None
    elif (value['state'] != 'UNKNOWN' or value['reason'] not in {'ORIGINAL_RECORDS_ABSENT','ORIGINAL_INTENT_ONLY'}
          or value['current_postimage_qualified'] is not False
          or value['current_reason'] not in {'ORIGINAL_COMPLETION_UNKNOWN','CURRENT_ACL_UNQUALIFIED'}):
        return None
    return value


def transport_observation(raw, context, *, returncode, timed_out=False, overflow=False,
                          local_unavailable=False):
    """Bounded canonical frames only. No raw stdout/stderr or retry authority."""
    result = dict(schema='mastermind.orch_original_read_transport.v1', root=ORCH_REPAIR_ROOT,
                  operation_id=ORCH_REPAIR_ORIGINAL_OPERATION, context_sha256=_sha(_canonical(context)),
                  phase='UNOBSERVED', transport_state='TIMED_OUT' if timed_out else 'PROCESS_RETURNED',
                  exit_code=returncode, result=None, retry_authorized=False,
                  replay=False, lifecycle_authority=False, stderr_retained=False)
    if local_unavailable:
        result['transport_state'] = 'LOCAL_PROCESS_UNAVAILABLE'
        return result
    if type(raw) is not bytes or not _valid_context(context) or overflow or len(raw) > FRAME_LIMIT:
        result['transport_state'] = 'OUTPUT_UNQUALIFIED'
        return result
    try:
        frames = []
        def pairs(items):
            value = {}
            for key, item in items:
                if key in value: raise ValueError('duplicate')
                value[key] = item
            return value
        lines = raw.splitlines(keepends=True)
        for line in lines:
            if not line.endswith(b'\n'):
                if timed_out and len(frames) < 2: break
                raise ValueError('incomplete')
            value = json.loads(line, object_pairs_hook=pairs)
            if (type(value) is not dict or set(value) != {'schema','context','kind','result'}
                    or value['schema'] != FRAME_SCHEMA or value['context'] != context
                    or _canonical(value)+b'\n' != line):
                raise ValueError('frame')
            frames.append(value)
        if len(frames) > 2: raise ValueError('count')
        if frames:
            first = frames[0]
            if first['kind'] == 'SCOPE_REFUSED' and len(frames) == 1:
                if (_qualified_result(first['result']) is None
                        or first['result']['state'] != 'HELD_OR_UNKNOWN'): raise ValueError('refusal')
                result.update(phase='SCOPE_REFUSED', result=_qualified_result(first['result']))
            elif first['kind'] == 'READ_ENTERED' and first['result'] is None:
                result['phase'] = 'READ_ENTERED'
                if len(frames) == 2:
                    value = _qualified_result(frames[1]['result'])
                    if frames[1]['kind'] != 'RESULT' or value is None: raise ValueError('result')
                    result.update(phase='RESULT_RETAINED', result=value)
            else: raise ValueError('order')
        if not timed_out and (returncode != 0 or result['phase'] not in {'RESULT_RETAINED','SCOPE_REFUSED'}):
            result['transport_state'] = 'RETURN_WITHOUT_QUALIFIED_RESULT'
    except (ValueError, UnicodeError, RecursionError, TypeError):
        result.update(phase='UNQUALIFIED', result=None, transport_state='OUTPUT_UNQUALIFIED')
    return result
