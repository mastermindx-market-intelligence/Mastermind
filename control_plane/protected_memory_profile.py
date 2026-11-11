"""Actual fixed installed profile for the protected Control execution owner.

The existing root-owned Control configuration gains one closed optional stanza.
A caller dictionary/boolean cannot issue this object. Source/profile facts do
not authenticate a served account or grant Linux data rights. Missing enrollment
refuses before preparing a case; ordinary UID501 paid configuration is untouched.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit
import weakref
from dataclasses import dataclass

from control_plane import native_memory_admission as admission

CONFIG = Path('/Library/Application Support/MastermindExecutive/config/control.json')
CREDENTIAL = Path('/Library/Application Support/MastermindExecutive/credentials/memory-model-01.json')
SCHEMA = 'mastermind.protected_memory_execution_profile.v1'
PROFILE = 'memory.sealed-model.v1'
POLICY = {'schema': 'mastermind.protected_memory_execution_policy.v1',
    'input': 'exact-native-issuer-packet', 'tools': [], 'callbacks': [],
    'delegation': False, 'private_owner_uid': 450, 'ordinary_uid501_transit': False,
    'result': 'private-original-with-scoped-view', 'max_input_bytes': 65536,
    'max_result_bytes': 65536, 'max_output_tokens': 8192}
_ISSUED = weakref.WeakKeyDictionary()
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z', re.ASCII)
_SHA = re.compile(r'[a-f0-9]{64}\Z', re.ASCII)


class MemoryProfileRefused(ValueError):
    def __init__(self): super().__init__('protected_memory_profile_unavailable')


def _refuse(): raise MemoryProfileRefused()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
        allow_nan=False).encode('utf-8')


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: _refuse()
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: _refuse())


def _read_config():
    from control_plane.codex_provider_realm import _native_open
    with _native_open(CONFIG) as (fd, info):
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 450
                or stat.S_IMODE(info.st_mode) != 0o440 or info.st_nlink != 1
                or not 1 <= info.st_size <= 4194304): _refuse()
        raw = bytearray()
        while len(raw) <= info.st_size:
            part = os.read(fd, min(65536, info.st_size + 1 - len(raw)))
            if not part: break
            raw.extend(part)
        identity=lambda s:(s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if len(raw) != info.st_size or identity(os.fstat(fd)) != identity(info): _refuse()
    return bytes(raw)


def _credential_metadata():
    # Do not read a secret while qualifying a profile. The fixed runner opens
    # this same protected slot only after current source/runtime admission.
    from control_plane.codex_provider_realm import _native_open
    with _native_open(CREDENTIAL) as (_, info):
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 450
                or stat.S_IMODE(info.st_mode) != 0o440 or info.st_nlink != 1
                or not 1 <= info.st_size <= 8192): _refuse()
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class ProtectedMemoryProfile:
    __slots__ = ('__weakref__',)
    def __new__(cls): _refuse()
    def __repr__(self): return '<ProtectedMemoryProfile redacted>'


@dataclass(frozen=True)
class _State:
    profile: bytes
    config_sha256: str
    credential_metadata: tuple
    pid: int


def validate_profile_document(value):
    """Closed public configuration DATA only; no installation or grant IO."""
    keys={'schema','profile_id','policy_sha256','worker_id','quota_class','provider',
          'model','account_ref','api_origin','credential_slot'}
    if (type(value) is not dict or set(value)!=keys or value['schema']!=SCHEMA
            or value['profile_id']!=PROFILE or value['provider']!='glm'
            or value['model'] not in ('glm-5.3','glm-5.3-flash')
            or value['policy_sha256']!=hashlib.sha256(canonical(POLICY)).hexdigest()
            or value['credential_slot']!='memory-model-01'):_refuse()
    for key in ('worker_id','quota_class','account_ref'):
        if type(value[key]) is not str or not _ID.fullmatch(value[key]):_refuse()
    if type(value['api_origin']) is not str or len(value['api_origin'])>512:_refuse()
    uri=urlsplit(value['api_origin'])
    if (uri.scheme!='https' or uri.hostname not in {'api.z.ai','open.bigmodel.cn'}
            or uri.username is not None or uri.password is not None or uri.port not in (None,443)
            or uri.query or uri.fragment or uri.path not in ('/api/paas/v4','/api/coding/paas/v4')
            or value['api_origin']!=uri.geturl()):_refuse()
    return _json(canonical(value))


def _qualify(claim, observed_owner):
    if os.geteuid() != 450: _refuse()
    locator = admission.require_memory_runtime_claim(claim)
    state = admission._ISSUED[claim]
    raw = _read_config()
    digest = hashlib.sha256(raw).hexdigest()
    if (type(observed_owner) is not dict
            or observed_owner.get('service_label') != 'com.mastermind.executive.control'
            or observed_owner.get('configuration_sha256') != digest): _refuse()
    document = _json(raw)
    if (type(document) is not dict or type(document.get('runtime_root')) is not str
            or document['runtime_root']!=str(state.runtime.store.root)):_refuse()
    read_access=document.get('memory_original_result_access')
    if (type(read_access) is dict and type(read_access.get('scope')) is dict
            and read_access['scope'].get('attempt_id')==state.lease.attempt.attempt_id):
        # A completed-result grant for this SAME future result must never
        # become a self-dependent ingredient of its original pre-input hash.
        _refuse()
    value = document.get('protected_memory_execution') if type(document) is dict else None
    value=validate_profile_document(value)
    job = state.runtime.jobs.get_job(state.lease.attempt.job_id)
    quota = state.runtime.workers.get_quota_class(value['worker_id'], value['quota_class'])
    worker = state.runtime.workers.get_worker(value['worker_id'])
    if (job is None or quota is None or worker is None
            or state.lease.attempt.worker_id != value['worker_id']
            or state.lease.attempt.quota_class != value['quota_class']
            or worker.worker_type != 'protected-memory-model'
            or quota.provider != 'glm' or quota.model != value['model']
            or worker.account_label != value['account_ref']
            or job.constraints.get('execution_profile_id') != PROFILE
            or job.constraints.get('execution_profile_digest') != hashlib.sha256(canonical(value)).hexdigest()
            or job.constraints.get('capability_policy_digest') != value['policy_sha256']
            or any(quota.metadata.get(k) != job.constraints.get(k) for k in (
                'execution_profile_id','execution_profile_digest','capability_policy_version','capability_policy_digest'))): _refuse()
    credential = _credential_metadata()
    if _read_config() != raw: _refuse()
    admission.require_memory_runtime_claim(claim)
    return canonical(value), digest, credential


def load_protected_memory_profile(claim, observed_owner) -> ProtectedMemoryProfile:
    try:
        raw, digest, credential = _qualify(claim, observed_owner)
        profile = object.__new__(ProtectedMemoryProfile)
        _ISSUED[profile] = _State(raw, digest, credential, os.getpid())
        return profile
    except Exception:
        raise MemoryProfileRefused() from None


def require_protected_memory_profile(profile, claim, observed_owner) -> dict:
    try:
        if type(profile) is not ProtectedMemoryProfile or profile not in _ISSUED: _refuse()
        state = _ISSUED[profile]
        raw, digest, credential = _qualify(claim, observed_owner)
        if (state.pid != os.getpid() or raw != state.profile or digest != state.config_sha256
                or credential != state.credential_metadata): _refuse()
        return _json(raw)
    except Exception:
        raise MemoryProfileRefused() from None
