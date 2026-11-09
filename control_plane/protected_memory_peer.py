"""Protected pre-input intent issuer on the existing Control peer boundary.

This object is not Linux source permission or provider admission. Its digest is
explicitly a NEW pre-input contract, never c82 participant_binding.v1 (which
already includes input SHA). No future packet/capability/result enters it.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import weakref
from dataclasses import dataclass

from control_plane import native_memory_admission as admission
from control_plane.executive_peer_identity import capture_peer_identity, require_installed_service_peer
from control_plane.executive_installed_peer import qualify_installed_peer

SCHEMA = 'mastermind.protected_memory_pre_input_intent.v1'
MODE = 'incumbent-protected-memory-v1'
_ISSUED = weakref.WeakKeyDictionary()


class ProtectedMemoryRefused(ValueError):
    def __init__(self):
        super().__init__('protected_memory_owner_required')


def _refuse():
    raise ProtectedMemoryRefused()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def _control(connection):
    if (os.geteuid() != 0 or type(connection) is not socket.socket
            or connection.fileno() < 0):
        _refuse()
    peer = capture_peer_identity(connection)
    binding = qualify_installed_peer(peer, role='control')
    context = require_installed_service_peer(peer, binding)
    if peer.euid != 450 or context.service_label != 'com.mastermind.executive.control':
        _refuse()
    return {'schema': 'mastermind.protected_memory_control_owner.v1', 'mode': MODE,
        'service_label': context.service_label, 'boot_id': context.real_boot_id,
        'audit_identity_sha256': context.audit_identity_digest,
        'installed_release': context.installed_release,
        'configuration_sha256': context.config_digest}


class ProtectedMemoryIntent:
    __slots__ = ('__weakref__',)

    def __new__(cls):
        _refuse()

    def __repr__(self):
        return '<ProtectedMemoryIntent private>'


@dataclass(frozen=True)
class _ControlState:
    claim: admission.MemoryRuntimeClaim
    original: bytes
    pid: int


@dataclass(frozen=True)
class _RootState:
    connection: socket.socket
    original: bytes
    pid: int


class ControlMemoryIntent:
    __slots__ = ('__weakref__',)

    def __new__(cls):
        _refuse()

    def __repr__(self):
        return '<ControlMemoryIntent private>'


_CONTROL_ISSUED = weakref.WeakKeyDictionary()


def observe_control_owner(connection) -> dict:
    """Safe root-observed metadata, NOT a portable credential or source grant."""
    try:
        return json.loads(canonical(_control(connection)))
    except Exception:
        raise ProtectedMemoryRefused() from None


def _owner_shape(value):
    keys = {'schema', 'mode', 'service_label', 'boot_id', 'audit_identity_sha256',
        'installed_release', 'configuration_sha256'}
    if (type(value) is not dict or set(value) != keys
            or value['schema'] != 'mastermind.protected_memory_control_owner.v1'
            or value['mode'] != MODE or value['service_label'] != 'com.mastermind.executive.control'):
        _refuse()
    # Only observed comparison data crosses IPC, never the nominal peer/lease.
    import re
    for key in ('audit_identity_sha256', 'configuration_sha256'):
        if type(value[key]) is not str or re.fullmatch('[a-f0-9]{64}', value[key]) is None:
            _refuse()
    if (type(value['installed_release']) is not str
            or re.fullmatch('[a-f0-9]{40}', value['installed_release']) is None
            or type(value['boot_id']) is not str or len(value['boot_id']) != 36):
        _refuse()
    return json.loads(canonical(value))


def _control_projection(claim, observed_owner):
    if os.geteuid() != 450:
        _refuse()
    locator = admission.require_memory_runtime_claim(claim)
    state = admission._ISSUED[claim]
    current, _, _ = admission._current(state.runtime, state.lease, process=state.process)
    return canonical({'schema': SCHEMA, 'owner': _owner_shape(observed_owner),
        'runtime_admission': json.loads(current),
        'original_operation_id': locator['operation_id'],
        'native_source_locator': locator['intent']})


def capture_control_memory_intent(claim, observed_owner) -> ControlMemoryIntent:
    """Control450 keeps its actual Runtime/opaque lease in the SAME process.

    Root-observed metadata is comparison data; the root receiver independently
    requalifies the live socket and Linux independently checks source admission.
    """
    try:
        raw = _control_projection(claim, observed_owner)
        value = object.__new__(ControlMemoryIntent)
        _CONTROL_ISSUED[value] = _ControlState(claim, raw, os.getpid())
        return value
    except Exception:
        raise ProtectedMemoryRefused() from None


def require_control_memory_intent(value) -> dict:
    try:
        if type(value) is not ControlMemoryIntent or value not in _CONTROL_ISSUED:
            _refuse()
        state = _CONTROL_ISSUED[value]
        old = json.loads(state.original)
        if (state.pid != os.getpid()
                or _control_projection(state.claim, old['owner']) != state.original):
            _refuse()
        return old
    except Exception:
        raise ProtectedMemoryRefused() from None


def _projection_shape(value):
    keys = {'schema', 'owner', 'runtime_admission', 'original_operation_id', 'native_source_locator'}
    if type(value) is not dict or set(value) != keys or value['schema'] != SCHEMA:
        _refuse()
    from common.native_memory_intent_contract import normalize_memory_runtime_intent
    locator = normalize_memory_runtime_intent({'schema': admission.SCHEMA,
        'operation_id': value['original_operation_id'], 'intent': value['native_source_locator']})
    _owner_shape(value['owner'])
    current = value['runtime_admission']
    fields = {'job_id', 'runtime_root', 'parent_job_id', 'owner_seat',
        'orchestration_provenance_digest', 'attempt_id', 'worker_id', 'quota_class',
        'fence', 'authority_policy_hash', 'claim_ref', 'locator_sha256'}
    if type(current) is not dict or set(current) != fields:
        _refuse()
    import re
    for key in ('job_id', 'runtime_root', 'attempt_id', 'worker_id', 'quota_class', 'owner_seat'):
        if type(current[key]) is not str or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', current[key]) is None:
            _refuse()
    if current['parent_job_id'] is not None and (type(current['parent_job_id']) is not str
            or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', current['parent_job_id']) is None):
        _refuse()
    for key in ('authority_policy_hash', 'locator_sha256'):
        if type(current[key]) is not str or re.fullmatch('[a-f0-9]{64}', current[key]) is None:
            _refuse()
    if (current['orchestration_provenance_digest'] is not None
            and (type(current['orchestration_provenance_digest']) is not str
                 or re.fullmatch('[a-f0-9]{64}', current['orchestration_provenance_digest']) is None)):
        _refuse()
    ref = current['claim_ref']
    if (type(current['fence']) is not int or not 1 <= current['fence'] <= 2**63-1
            or type(ref) is not dict or set(ref) != {'schema', 'event_id', 'sha256'}
            or ref['schema'] != 'mastermind.runtime_claim_ref.v1'
            or type(ref['event_id']) is not int or not 1 <= ref['event_id'] <= 2**63-1
            or type(ref['sha256']) is not str or re.fullmatch('[a-f0-9]{64}', ref['sha256']) is None
            or current['locator_sha256'] != hashlib.sha256(canonical(locator)).hexdigest()):
        _refuse()
    return canonical(value)


def accept_protected_memory_intent(projection, connection) -> ProtectedMemoryIntent:
    """Root accepts a projection ONLY from its actual qualified Control peer.

    This is the same private producer/receiver boundary as incumbent Control
    start projection. A dictionary has no authority outside that transport.
    Root never serializes/reconstructs the Control process's opaque Runtime
    claim. Control must recheck its own handle before/after every exchange.
    """
    try:
        before = _control(connection)
        raw = _projection_shape(projection)
        if projection['owner'] != before or _control(connection) != before:
            _refuse()
        value = object.__new__(ProtectedMemoryIntent)
        _ISSUED[value] = _RootState(connection, raw, os.getpid())
        return value
    except Exception:
        raise ProtectedMemoryRefused() from None


def require_protected_memory_intent(value) -> tuple[dict, dict]:
    """Fresh same-Control peer check; independent Linux grant remains mandatory."""
    try:
        if type(value) is not ProtectedMemoryIntent or value not in _ISSUED:
            _refuse()
        state = _ISSUED[value]
        material = json.loads(state.original)
        if state.pid != os.getpid() or _control(state.connection) != material['owner']:
            _refuse()
        digest = hashlib.sha256(state.original).hexdigest()
        ref = {'schema': SCHEMA, 'sha256': digest, 'bytes': len(state.original)}
        intent = dict(material['native_source_locator'], participant_binding_sha256=digest)
        request = {'schema': 'research_factory.market_memory_e0_native_issuer_request.v1',
            'action': 'prepare_case', 'operation_id': material['original_operation_id'], 'intent': intent}
        return request, ref
    except Exception:
        raise ProtectedMemoryRefused() from None
