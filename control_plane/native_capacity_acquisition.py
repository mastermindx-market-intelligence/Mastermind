"""Fixed Control-to-Macro acquisition, default absent and read-only.

The context is a process-local composition seam, not a wire credential. The
underlying owner still authenticates kernel peer, root custody, nonce, config,
source registration, enrollment and boot on every acquisition. No arbitrary
producer import, callback, supplied observation, provider call or V1 migration.
"""
from __future__ import annotations

import contextvars
import hashlib
import os
import re
import time
import types

_ACTIVE = contextvars.ContextVar('native_capacity_macro_owner', default=None)
_MINT = object()
_HEX = re.compile(r'[0-9a-f]{64}')
_COMMIT = re.compile(r'[0-9a-f]{40}')
PRODUCER_RELATIVE = 'engine/provider_capacity_v2.py'


class NativeCapacityAcquisitionError(ValueError):
    pass


def _refuse(code):
    raise NativeCapacityAcquisitionError(code)


class NativeCapacitySource:
    """Constructed from protected startup definition; no production default."""
    def __init__(self, mint, probe, bindings, release, digest):
        if mint is not _MINT:
            _refuse('CAPACITY_OWNER_REQUIRED')
        self._mint, self.probe, self.bindings = mint, probe, bindings
        self.release, self.digest = release, digest

    @classmethod
    def from_startup(cls, probe, bindings):
        from control_plane.fabric_attended_canary import AttendedControlProbeSource
        from control_plane.executive_fabric_composition import FabricBindingSource
        if type(probe) is not AttendedControlProbeSource or type(bindings) is not FabricBindingSource:
            _refuse('CAPACITY_OWNER_REQUIRED')
        if len(bindings.bindings) != 1:
            _refuse('CAPACITY_PHYSICAL_OWNER_REQUIRED')
        physical, = bindings.bindings
        raw, _, _ = probe.configuration(physical)
        stanza = raw.get('native_capacity_v2')
        if stanza is None:
            return None
        if (type(stanza) is not dict or set(stanza) != {'macro_release', 'producer_sha256'}
                or type(stanza['macro_release']) is not str
                or _COMMIT.fullmatch(stanza['macro_release']) is None
                or type(stanza['producer_sha256']) is not str
                or _HEX.fullmatch(stanza['producer_sha256']) is None):
            _refuse('CAPACITY_SOURCE_PIN_INVALID')
        return cls(_MINT, probe, bindings, stanza['macro_release'], stanza['producer_sha256'])

    def _physical(self):
        physical, = self.bindings.bindings
        if (physical.worker_id != 'minimax-finite-01' or physical.provider != 'minimax'
                or self.bindings(physical.host_ref, physical.worker_id) != physical):
            _refuse('CAPACITY_PHYSICAL_SOURCE_CHANGED')
        raw, _, _ = self.probe.configuration(physical)
        if raw.get('native_capacity_v2') != {'macro_release': self.release, 'producer_sha256': self.digest}:
            _refuse('CAPACITY_SOURCE_CHANGED')
        return physical

    def _read_producer(self):
        from control_plane.codex_provider_realm import _native_open
        from ops.executive_os.capacity_source_contract import SYSTEM_ROOT
        path = SYSTEM_ROOT / 'capacity-sources' / 'macro' / self.release / PRODUCER_RELATIVE
        # Hold every canonical component; no symlink, writable ancestor, ACL,
        # supplied sys.path or source from a different release is executable.
        with _native_open(path) as (fd, _):
            content = os.read(fd, 65537)
        if len(content) > 65536 or hashlib.sha256(content).hexdigest() != self.digest:
            _refuse('CAPACITY_PRODUCER_BYTES_CHANGED')
        return content

    async def acquire(self):
        if type(self) is not NativeCapacitySource or self._mint is not _MINT or _ACTIVE.get() is not None:
            _refuse('CAPACITY_OWNER_REQUIRED')
        started = time.monotonic()
        wall_started = time.time()
        physical = self._physical()
        content = self._read_producer()
        module = types.ModuleType('_sealed_macro_native_capacity')
        exec(compile(content, PRODUCER_RELATIVE, 'exec'), module.__dict__)
        token = _ACTIVE.set(self)
        try:
            value = await module.build_snapshot()
        finally:
            _ACTIVE.reset(token)
        if (self._physical() != physical or self._read_producer() != content
                or not 0 <= time.monotonic() - started <= 15
                or abs((time.time()-wall_started)-(time.monotonic()-started)) > 2):
            _refuse('CAPACITY_ACQUISITION_CHANGED_OR_EXPIRED')
        from control_plane.native_capacity_v2 import validate_snapshot
        return validate_snapshot(value, now_ms=time.time_ns() // 1_000_000)


async def _acquire_for_macro():
    owner = _ACTIVE.get()
    if type(owner) is not NativeCapacitySource or owner._mint is not _MINT:
        _refuse('CAPACITY_SOURCE_UNBOUND')
    from ops.executive_os.capacity_source_contract import acquire_control_native_registration
    physical = owner._physical()
    before = acquire_control_native_registration(owner.probe, physical)
    if before['source_release_commit'] != owner.release:
        _refuse('CAPACITY_REGISTRATION_RELEASE_CHANGED')
    observation = await owner.probe.native_observation(physical)
    if (acquire_control_native_registration(owner.probe, physical) != before
            or owner._physical() != physical):
        _refuse('CAPACITY_REGISTRATION_CHANGED')
    return {'registration': before, 'observation': observation,
        'worker_source_config_digest': physical.worker_source_config_digest,
        'producer_sha256': owner.digest}
