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


