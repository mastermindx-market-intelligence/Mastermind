"""Compose the existing MH1 transport for one original Fabric Attempt.

This owns no launch, lease, host selection, credential enrollment or retry.
Only an immutable installed Fabric binding can select this transport. The
remote gateway authenticates Control and forwards to its fixed Fabric bridge;
that bridge constructs ControlStartAuthority from its real kernel peer.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import ipaddress
import json
import math
import stat
from pathlib import Path
from types import MappingProxyType

from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import BrokerTransportBinding

FABRIC_OPERATIONS = frozenset({'start', 'status', 'collect', 'cancel', 'validate', 'attended-secret-canary',
                              'assignment-seal', 'assignment-seal-finalize'})
_FIELDS = frozenset({'host_ref', 'worker_id', 'physical_binding_sha256',
    'endpoint_host', 'endpoint_port', 'ca_path', 'client_cert_path', 'client_key_path',
    'expected_server_fingerprint', 'timeout_seconds'})
_BINDING_FIELDS = frozenset({'root_id', 'job_id', 'attempt_id',
                            'effective_grant_digest', 'commission_sha256'})


def _refuse():
    from control_plane.executive_fabric_composition import FabricCompositionError
    raise FabricCompositionError('Pinned Fabric remote transport is unavailable or changed')


def _file_identity(path, *, private=False):
    from control_plane.executive_fabric_composition import _absolute_path, _trusted_parent_chain, _identity
    path = _absolute_path(str(path))
    try:
        _trusted_parent_chain(path)
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or info.st_mode & 0o022 or info.st_size <= 0
                or (private and info.st_mode & 0o007)):
            _refuse()
        return _identity(info)
    except OSError:
        _refuse()


@dataclasses.dataclass(frozen=True)
class FabricRemoteTransport:
    binding: BrokerTransportBinding
    file_identities: tuple[tuple[int, ...], ...]

    @classmethod
    def from_document(cls, raw, physical):
        if (type(raw) is not dict or set(raw) != _FIELDS
                or raw['host_ref'] != physical.host_ref
                or raw['worker_id'] != physical.worker_id
                or raw['physical_binding_sha256'] != physical.digest
                or type(raw['endpoint_host']) is not str
                or any(type(raw[name]) is not str for name in
                       ('ca_path', 'client_cert_path', 'client_key_path'))):
            _refuse()
        try:
            host = ipaddress.ip_address(raw['endpoint_host'])
            if host.is_global or host.is_multicast or host.is_unspecified:
                _refuse()
            timeout = raw['timeout_seconds']
            if (type(timeout) not in (int, float) or not math.isfinite(timeout)
                    or not 0.1 <= timeout <= 3600):
                _refuse()
            paths = tuple(Path(raw[name]) for name in
                          ('ca_path', 'client_cert_path', 'client_key_path'))
            identities = tuple(_file_identity(path, private=(i == 2))
                               for i, path in enumerate(paths))
            binding = BrokerTransportBinding(
                endpoint=(str(host), raw['endpoint_port']),
                ca_path=paths[0], client_cert_path=paths[1], client_key_path=paths[2],
                expected_server_fingerprint=raw['expected_server_fingerprint'],
                timeout_seconds=timeout)
            return cls(binding, identities)
        except (ValueError, TypeError, KeyError, OSError):
            _refuse()

    def require_current(self):
        paths = (self.binding.ca_path, self.binding.client_cert_path, self.binding.client_key_path)
        if tuple(_file_identity(path, private=(i == 2))
                 for i, path in enumerate(paths)) != self.file_identities:
            _refuse()


class PinnedFabricRemoteClient:
    """One original Attempt over MH1; no fallback to local or another host."""

    def __init__(self, source, physical, payload, transport):
        binding = payload.get('binding') if type(payload) is dict else None
        if (type(binding) is not dict or set(binding) != _BINDING_FIELDS
                or any(type(v) is not str or not v for v in binding.values())
                or payload.get('physical_binding_sha256') != physical.digest):
            _refuse()
        self._source, self._physical, self._transport = source, physical, transport
        self._binding = MappingProxyType(dict(binding))
        # An MH1 message coordinate, never a new root, operation owner or grant.
        message_id = 'fabric-' + hashlib.sha256(json.dumps(
            [physical.digest, binding], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        identity = dict(host_ref=physical.host_ref, worker_id=physical.worker_id,
                        job_id=binding['job_id'], attempt_id=binding['attempt_id'],
                        operation_id=message_id)
        self.identity = MappingProxyType(identity)
        self._client = RemoteWorkerBrokerClient(transport.binding, identity,
                                                allowed_operations=FABRIC_OPERATIONS)

    def bind_payload_identity(self, *, session_epoch_id, process_generation_id):
        """Retain the incumbent optional, exactly-once Runtime generation fence."""
        self._client.bind_payload_identity(session_epoch_id=session_epoch_id,
                                           process_generation_id=process_generation_id)

    def _require(self, operation, payload):
        if (operation not in FABRIC_OPERATIONS or type(payload) is not dict
                or payload.get('binding') != dict(self._binding)
                or payload.get('physical_binding_sha256') != self._physical.digest
                or self._source(self._physical.host_ref, self._physical.worker_id) != self._physical):
            _refuse()
        self._transport.require_current()
        # Retain the existing recursive MH1 host/worker/Job/Attempt/run check,
        # even before a client or test seam is invoked.
        from control_plane.remote_worker_transport import payload_retargets_authority
        if payload_retargets_authority(operation, payload, self.identity,
                                       bound_payload_identity=self._client.bound_payload_identity):
            _refuse()

    async def request(self, operation, payload, *, timeout_seconds=None, foreground_start_receipt=None):
        self._require(operation, payload)
        try:
            options = {} if foreground_start_receipt is None else dict(foreground_start_receipt=foreground_start_receipt)
            result = await self._client.request(operation, payload, timeout_seconds=timeout_seconds, **options)
        except asyncio.CancelledError as exc:
            # The inner await may already have written the original command.
            # Without its classified no-effect response, cancellation cannot
            # authorize another start. Read-only cancellation stays ordinary.
            if not RemoteWorkerBrokerClient._operation_is_observational(operation, payload):
                from control_plane.remote_worker_transport import TransportError, TransportEffect
                raise TransportError('fabric_request_cancelled', TransportEffect.EFFECT_UNKNOWN) from exc
            raise
        try:
            self._require(operation, payload)
        except Exception as exc:
            # A changed trust source invalidates the response, not the effect
            # already sent to the original owner. Never classify it as retryable.
            if not RemoteWorkerBrokerClient._operation_is_observational(operation, payload):
                from control_plane.remote_worker_transport import TransportError, TransportEffect
                raise TransportError('fabric_binding_changed', TransportEffect.EFFECT_UNKNOWN) from exc
            raise
        return result

    def request_sync(self, operation, payload, *, timeout_seconds=None):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.request(operation, payload, timeout_seconds=timeout_seconds))
        from control_plane.remote_worker_transport import TransportError, TransportEffect
        raise TransportError('sync_context_invalid', TransportEffect.NO_EFFECT)
