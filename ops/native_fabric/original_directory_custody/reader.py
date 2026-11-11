"""Prospective original-directory metadata action in the incumbent native owner.

This module installs no owner factory, CLI, transport route or grant. Its default
owner denies the action. Existing CURRENT-source grants and caller root labels
cannot authorize it. The positive tests use explicit inert trusted-owner premises,
not a present runtime admission. No artifact file is ever opened by the engine.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import pwd
from pathlib import Path
import re
import stat
from types import MethodType

import artifact_production as production
import artifact_reader as artifacts
from current_source_observation import NativeInvocationOwner

SCHEMA = 'mastermind.original_directory_metadata.v1'
ACTION = 'original_collection_directory_metadata'
RUN = 'prophet-plan-review-component-build-01a11e89-20261015-01'
ROOT = '01a11e89-b35d-7a81-9404-5fce2c6170cb'
HOST = 'ubuntu3'
ORIGINAL_REQUEST_SHA256 = '1071c59b3cea43fc5ea15399c1d3bdd27ac2cbf52e61bf7309c7d8fc5ddff54f'
ORIGINAL_BINDING_SHA256 = '77071620d7589bf73bd9868205a7deb85ddc6979a9b38eed1b6a6455d529e6e4'
ORIGINAL_REFUSAL_SHA256 = 'bf9bc52a2a8d8d088cb3fb5ef4208002d2ddc5fd2c23d08ef1b90d0d7c683681'
MAX_RESPONSE = 8192


class Refused(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def request():
    # The retained read-request is metadata, not a recovered packet or result.
    contract = {'schema': 'mastermind.fabric_artifact_production.v1',
        'root': ROOT, 'parent': ROOT, 'run_id': RUN,
        'names': ['plan-review-component.patch'],
        'body_sha256': '9c532501e8cfb40b4575be1f92df78debbc49784d356f2ab1823c2ffc140d551',
        'support_digest': '5fc2034ca5e4b16a8d30a802beb5fa5c4697c44a0a2e10aa09d56f57ec722f62'}
    return {'schema': SCHEMA, 'action': ACTION,
        'directory_scope': 'ACCOUNT_LANES_EXT_RESULT_DIRECTORY', 'run_id': RUN, 'root': ROOT,
        'parent': ROOT, 'host': HOST, 'contract': contract,
        'original_request_sha256': ORIGINAL_REQUEST_SHA256,
        'original_binding_sha256': ORIGINAL_BINDING_SHA256,
        'original_refusal_sha256': ORIGINAL_REFUSAL_SHA256}


def validate_request(value):
    if type(value) is not dict or canonical(value) != canonical(request()):
        raise Refused('original_directory_scope_refused')
    production.validate_contract(value['contract'])
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class MetadataActionView:
    schema: str
    action: str
    request_sha256: str
    run_id: str
    root: str
    parent: str
    host: str
    directory_scope: str
    artifact_namespace: str


@dataclass(frozen=True)
class OwnerTransportBinding:
    """Owner-rederived account correlation; this tuple is not a grant."""
    host: str
    ssh_alias: str
    account_scope_sha256: str
    remote_uid: int


class OriginalDirectoryOwner(NativeInvocationOwner):
    """Extension of the existing trusted native owner, default-deny.

    Only a real incumbent native registration may supply an implementation.
    It must verify the actual current OS/tool action permission, original
    metadata pins, calling identity, source closure and same SSH account; claim
    this separately admitted action through the existing exclusive delivery
    intent BEFORE returning True, and refuse any interrupted/duplicate claim.
    An ordinary CURRENT-source owner is deliberately insufficient.

    No implementation is installed by this component. Python nominal typing is
    process integrity, not authentication against arbitrary in-process code.
    """
    def admit_original_directory_metadata(self, view, invoking_uid):
        return False

    def original_directory_metadata_current(self, view, invoking_uid):
        return False

    def original_directory_transport_binding(self, view, invoking_uid):
        return None

    def original_directory_metadata_transport(self, binding, value):
        raise Refused('original_directory_owner_registration_required')


def _binding(owner, view, uid):
    binding = owner.original_directory_transport_binding(view, uid)
    if (type(binding) is not OwnerTransportBinding or binding.host != HOST
            or type(binding.ssh_alias) is not str
            or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', binding.ssh_alias) is None
            or type(binding.account_scope_sha256) is not str
            or re.fullmatch(r'[a-f0-9]{64}', binding.account_scope_sha256) is None
            or type(binding.remote_uid) is not int or binding.remote_uid <= 0):
        raise Refused('original_directory_account_unbound')
    return binding


def inspect_metadata(value, *, owner=None):
    try:
        return _inspect_registered(value, owner=owner)
    except Refused:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise Refused('original_directory_owner_unavailable') from None


def _inspect_registered(value, *, owner=None):
    """Owner-only integration seam, not a public execution command.

    The transport must be a method of the same registered native owner on the
    incumbent carrier; callers cannot supply or substitute a transport callback.
    Until that real registration exists the action is unavailable, even when
    a request carries the right original root. No automatic invocation occurs.
    """
    detached = artifacts.strict_json(canonical(value))
    digest = validate_request(detached)
    view = MetadataActionView(SCHEMA, ACTION, digest, RUN, ROOT, ROOT, HOST,
                              detached['directory_scope'], production.directory(detached['contract']))
    uid = os.getuid()
    if not isinstance(owner, OriginalDirectoryOwner) or uid <= 0:
        raise Refused('original_directory_owner_registration_required')
    transport = owner.original_directory_metadata_transport
    if (type(transport) is not MethodType or transport.__self__ is not owner
            or transport.__func__ is OriginalDirectoryOwner.original_directory_metadata_transport):
        raise Refused('original_directory_owner_registration_required')
    if owner.admit_original_directory_metadata(view, uid) is not True:
        raise Refused('original_directory_action_not_admitted')
    bound = _binding(owner, view, uid)
    def current():
        if (owner.original_directory_metadata_current(view, uid) is not True
                or _binding(owner, view, uid) != bound
                or os.getuid() != uid
                or type(owner.original_directory_metadata_transport) is not MethodType
                or owner.original_directory_metadata_transport.__self__ is not owner
                or owner.original_directory_metadata_transport.__func__ is not transport.__func__):
            raise Refused('original_directory_admission_withdrawn')
    current()
    try:
        raw = transport(bound, detached)
        result = validate_response(raw, detached)
        if any(row['invoking_uid'] != bound.remote_uid for row in result['directories']):
            raise Refused('original_directory_account_unconfirmed')
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise Refused('original_directory_observation_unconfirmed') from None
    current()
    return result


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_mtime_ns, info.st_ctime_ns)


def _metadata(value):
    """Observe only the directory chain used by incumbent remote_read.

    Same account pwd source, no HOME or request path override. The original
    direct directory_owner_or_mode class comes from this DirectoryChain;
    artifact file read failures are a different closed refusal class.
    """
    value = artifacts.strict_json(canonical(value))
    digest = validate_request(value)
    uid = os.getuid(); descriptors = []; edges = []; bad_edge = None
    result = {'schema': SCHEMA, 'request_sha256': digest, 'state': 'UNAVAILABLE',
        'reason': 'FILESYSTEM_REFUSED', 'directories': [],
        'artifact_files_opened': 0, 'artifact_bytes_read': 0,
        'permission_changed': False, 'execution_replayed': False,
        'outcome_accepted': False, 'retry_authorized': False}
    def classify(info):
        if stat.S_ISLNK(info.st_mode):return 'SYMLINK'
        if not stat.S_ISDIR(info.st_mode):return 'NOT_DIRECTORY'
        if info.st_uid not in {0, uid}:return 'OWNER_MISMATCH'
        if info.st_mode & 0o022:return 'GROUP_OR_OTHER_WRITABLE'
        return None
    def metadata(info, depth, home_depth):
        component = ('FILESYSTEM_ROOT' if depth == 0 else
            'HOME_ANCESTOR' if depth < home_depth else
            'ACCOUNT_HOME' if depth == home_depth else
            ('LANES','EXT','RESULT_DIRECTORY')[depth-home_depth-1])
        return {'component': component, 'depth': depth, 'uid': info.st_uid,
            'invoking_uid': uid, 'mode': stat.S_IMODE(info.st_mode),
            'kind': 'SYMLINK' if stat.S_ISLNK(info.st_mode) else
                    'DIRECTORY' if stat.S_ISDIR(info.st_mode) else 'OTHER'}
    try:
        if uid <= 0 or os.geteuid() != uid:
            result['reason'] = 'ACCOUNT_HOME_UNQUALIFIED'
            return result
        home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
        if (not home.is_absolute() or not 1 <= len(home.parts)-1 <= 16
                or any(x in {'.','..'} for x in home.parts[1:])):
            result['reason'] = 'ACCOUNT_HOME_UNQUALIFIED'
            return result
        # This is exactly the non-plain original collector's fixed layout.
        parts = (*home.parts[1:], 'lanes', 'ext', 'lanes')
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
        descriptors.append((fd, None))
        info = os.fstat(fd); descriptors[-1] = (fd, info)
        reason = classify(info); selected = metadata(info, 0, len(home.parts)-1)
        if reason is None:
            for depth, name in enumerate(parts, 1):
                parent = descriptors[-1][0]
                named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                reason = classify(named)
                selected = metadata(named, depth, len(home.parts)-1)
                if reason is not None:
                    bad_edge = (parent, name, named)
                    break
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                descriptors.append((child, None))
                held = os.fstat(child); descriptors[-1] = (child, held); edges.append((parent, name, held))
                if _identity(held) != _identity(named):raise Refused('directory_changed')
        for held, before in descriptors:
            if _identity(os.fstat(held)) != _identity(before):raise Refused('directory_changed')
        for parent, name, before in edges + ([bad_edge] if bad_edge else []):
            if _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != _identity(before):
                raise Refused('directory_changed')
        if (_identity(os.stat('/', follow_symlinks=False)) != _identity(descriptors[0][1])
                or os.getuid() != uid or os.geteuid() != uid
                or pwd.getpwuid(uid).pw_dir != str(home)):
            raise Refused('directory_changed')
        result.update(state='UNSAFE' if reason else 'SAFE_AT_OBSERVATION', reason=reason,
                      directories=[selected])
    except FileNotFoundError:
        result['reason'] = 'DIRECTORY_MISSING'
    except Refused:
        result['reason'] = 'DIRECTORY_CHANGED'
    except (OSError, KeyError, ValueError):
        pass
    finally:
        for fd, _ in reversed(descriptors):
            try:
                os.close(fd)
            except OSError:
                result.update(state='UNAVAILABLE', reason='FILESYSTEM_REFUSED', directories=[])
    return result


def validate_response(raw, value):
    digest = validate_request(value)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE:
        raise Refused('original_directory_response_limit')
    row = artifacts.strict_json(raw)
    fixed = {'schema': SCHEMA, 'request_sha256': digest, 'artifact_files_opened': 0,
        'artifact_bytes_read': 0, 'permission_changed': False,
        'execution_replayed': False, 'outcome_accepted': False, 'retry_authorized': False}
    if (type(row) is not dict or set(row) != set(fixed) | {'state','reason','directories'}
            or any(type(row.get(k)) is not type(v) or row.get(k) != v for k,v in fixed.items())):
        raise Refused('original_directory_response_invalid')
    reason = row['reason']; directories = row['directories']
    if type(row['state']) is not str or (reason is not None and type(reason) is not str):
        raise Refused('original_directory_response_invalid')
    if row['state'] == 'UNAVAILABLE':
        if reason not in {'FILESYSTEM_REFUSED','DIRECTORY_MISSING','DIRECTORY_CHANGED','ACCOUNT_HOME_UNQUALIFIED'} or directories != []:
            raise Refused('original_directory_response_invalid')
        return row
    if (type(directories) is not list or len(directories) != 1
            or type(directories[0]) is not dict
            or set(directories[0]) != {'component','depth','uid','invoking_uid','mode','kind'}
            or type(directories[0]['component']) is not str
            or directories[0]['component'] not in {'FILESYSTEM_ROOT','HOME_ANCESTOR','ACCOUNT_HOME','LANES','EXT','RESULT_DIRECTORY'}
            or type(directories[0]['depth']) is not int or not 0 <= directories[0]['depth'] <= 19
            or any(type(directories[0][k]) is not int or directories[0][k] < 0 for k in ('uid','invoking_uid','mode'))
            or stat.S_IMODE(directories[0]['mode']) != directories[0]['mode']):
        raise Refused('original_directory_response_invalid')
    meta = directories[0]
    if type(meta['kind']) is not str or meta['kind'] not in {'DIRECTORY','SYMLINK','OTHER'}:
        raise Refused('original_directory_response_invalid')
    expected = ('SYMLINK' if meta['kind'] == 'SYMLINK'
                else 'NOT_DIRECTORY' if meta['kind'] == 'OTHER'
                else 'OWNER_MISMATCH' if meta['uid'] not in {0, meta['invoking_uid']}
                else 'GROUP_OR_OTHER_WRITABLE' if meta['mode'] & 0o022 else None)
    if (row['state'] != ('UNSAFE' if expected else 'SAFE_AT_OBSERVATION') or reason != expected
            or (expected is None and meta['component'] != 'RESULT_DIRECTORY')):
        raise Refused('original_directory_response_invalid')
    return row
