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
class _State:
    connection: socket.socket
    claim: admission.MemoryRuntimeClaim
    original: bytes
    pid: int


def _material(claim, connection):
    before = _control(connection)
    locator = admission.require_memory_runtime_claim(claim)
    state = admission._ISSUED[claim]
    current, _, _ = admission._current(state.runtime, state.lease)
    after = _control(connection)
    if before != after:
        _refuse()
    return canonical({'schema': SCHEMA, 'owner': before,
        'runtime_admission': json.loads(current),
        'original_operation_id': locator['operation_id'],
        'native_source_locator': locator['intent']})


def capture_protected_memory_intent(claim, connection) -> ProtectedMemoryIntent:
    """Only actual root helper + qualified live Control peer + real Runtime claim.

    Native source provenance is correlation until the independently enrolled
    Linux grant matches it. This function performs no source read/reservation,
    child-row/budget consumption, key access or launch.
    """
    try:
        raw = _material(claim, connection)
        result = object.__new__(ProtectedMemoryIntent)
        _ISSUED[result] = _State(connection, claim, raw, os.getpid())
        return result
    except Exception:
        raise ProtectedMemoryRefused() from None


def require_protected_memory_intent(value) -> tuple[dict, dict]:
    """Fresh owner/runtime bracket, yielding the closed request and audit ref.

    Both remain comparison data; only the actual fixed Linux exchange may issue
    a NativeCaseCapability. They cannot authorize the ordinary UID501 backend.
    """
    try:
        if type(value) is not ProtectedMemoryIntent or value not in _ISSUED:
            _refuse()
        state = _ISSUED[value]
        if os.getpid() != state.pid or _material(state.claim, state.connection) != state.original:
            _refuse()
        material = json.loads(state.original)
        digest = hashlib.sha256(state.original).hexdigest()
        ref = {'schema': SCHEMA, 'sha256': digest, 'bytes': len(state.original)}
        intent = dict(material['native_source_locator'], participant_binding_sha256=digest)
        request = {'schema': 'research_factory.market_memory_e0_native_issuer_request.v1',
            'action': 'prepare_case', 'operation_id': material['original_operation_id'], 'intent': intent}
        return request, ref
    except Exception:
        raise ProtectedMemoryRefused() from None
