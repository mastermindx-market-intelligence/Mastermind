"""Immutable root-installed data composition for exact attended Fabric routes.

This module selects no host, imports no configured code, and owns no lifecycle.
Every lookup revalidates the one approved file before returning its fixed route.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from control_plane.executive_fabric_adapter import FabricHostBinding
from control_plane.executive_worker_broker import BrokerStateError

CONFIG_SCHEMA_VERSION = "mastermind.executive_fabric_bindings/v1"
REMOTE_CONFIG_SCHEMA_VERSION = "mastermind.executive_fabric_bindings/v2"
HOST_READ_CONFIG_SCHEMA_VERSION = "mastermind.executive_fabric_bindings/v3"
SECRETARY_CONFIG_SCHEMA_VERSION = "mastermind.executive_fabric_bindings/v4"
HERMES_SECRETARY_HOST_SCHEMA = "mastermind.hermes_secretary_host_binding/v1"
CONVERSATION_CONFIG_SCHEMA_VERSION = "mastermind.executive_fabric_bindings/v5"
HERMES_META_HOST_SCHEMA = "mastermind.hermes_meta_host_binding/v1"
HERMES_HOST_READ_SCHEMA = "mastermind.hermes_role_metadata_host_binding/v1"
NATIVE_CONFIG_SCHEMA_VERSION = "mastermind.executive_fabric_bindings/v6"
NATIVE_OPERATOR_HOST_SCHEMA = "mastermind.dsh_native_operator_host_binding/v1"
MAX_CONFIG_BYTES = 64 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_BINDING_FIELDS = frozenset(field.name for field in dataclasses.fields(FabricHostBinding))


class FabricCompositionError(BrokerStateError):
    """The pinned composition is unavailable, changed, or untrusted."""


def _absolute_path(value: object) -> Path:
    if type(value) is not str or not value or "\x00" in value:
        raise FabricCompositionError("Fabric composition path is invalid")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        raise FabricCompositionError("Fabric composition paths must be canonical and absolute")
    return path


def _trusted_parent_chain(path: Path) -> None:
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise FabricCompositionError("Fabric composition parent is not root-controlled")


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_uid, info.st_gid, info.st_mode, info.st_nlink)


def _read_pinned(path: Path, expected_sha256: str) -> tuple[bytes, tuple[int, ...]]:
    descriptor = None
    try:
        _trusted_parent_chain(path)
        visible = path.lstat()
        if not stat.S_ISREG(visible.st_mode):
            raise FabricCompositionError("Fabric composition must be a regular file, never a symlink")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0
                or before.st_mode & 0o022 or not 0 < before.st_size <= MAX_CONFIG_BYTES):
            raise FabricCompositionError("Fabric composition is not a bounded root-owned protected file")
        raw = bytearray()
        while len(raw) <= MAX_CONFIG_BYTES:
            part = os.read(descriptor, MAX_CONFIG_BYTES + 1 - len(raw))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(descriptor)
        if (len(raw) != before.st_size or len(raw) > MAX_CONFIG_BYTES
                or _identity(visible) != _identity(before)
                or _identity(before) != _identity(after)
                or _identity(after) != _identity(path.lstat())):
            raise FabricCompositionError("Fabric composition identity changed while reading")
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise FabricCompositionError("Fabric composition hash differs from its approved source")
        return bytes(raw), _identity(after)
    except OSError as exc:
        raise FabricCompositionError("Root-installed Fabric composition is unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _pairs(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise FabricCompositionError("Duplicate Fabric composition JSON keys are forbidden")
        document[key] = value
    return document


def _nonfinite(value):
    raise FabricCompositionError("Nonfinite Fabric composition JSON values are forbidden")


def _document(raw: bytes):
    try:
        document = json.loads(raw.decode("utf-8", errors="strict"),
                              object_pairs_hook=_pairs, parse_constant=_nonfinite)
        # This also refuses overflowed numeric literals and lone surrogates.
        json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise FabricCompositionError("Fabric composition is not bounded strict UTF-8 JSON") from exc
    return document


def _bindings(raw: bytes) -> tuple[FabricHostBinding, ...]:
    document = _document(raw)
    if (type(document) is not dict or set(document) != {"schema_version", "bindings"}
            or document["schema_version"] != CONFIG_SCHEMA_VERSION
            or type(document["bindings"]) is not list or not document["bindings"]):
        raise FabricCompositionError("Fabric composition document differs from its closed schema")
    bindings = []
    keys = set()
    for value in document["bindings"]:
        if type(value) is not dict or set(value) != _BINDING_FIELDS:
            raise FabricCompositionError("Fabric binding differs from its closed dataclass fields")
        for name, item in value.items():
            if name not in {"worker_uid", "worker_gid", "bridge_uid"}:
                if type(item) is not str or not item or any(ord(char) < 32 for char in item):
                    raise FabricCompositionError("Fabric binding contains an invalid string")
        for name in ("socket_path", "provider_home"):
            _absolute_path(value[name])
        try:
            binding = FabricHostBinding(**value)
        except (BrokerStateError, TypeError, ValueError) as exc:
            raise FabricCompositionError("Fabric binding physical identity is invalid") from exc
        key = (binding.host_ref, binding.worker_id)
        if key in keys:
            raise FabricCompositionError("Duplicate exact Fabric host/worker binding is forbidden")
        keys.add(key)
        bindings.append(binding)
    return tuple(bindings)


@dataclasses.dataclass(frozen=True)
class HermesHostObservationBinding:
    """One pinned host-read route, with no Worker or Attempt identity."""

    host_ref: str
    transport: object
    expected_host_binding_sha256: str
    expected_implementation_sha: str

    @classmethod
    def from_document(cls, value):
        fields = {'schema', 'host_ref', 'transport', 'expected_host_binding_sha256',
                  'expected_implementation_sha'}
        if (type(value) is not dict or set(value) != fields
                or value['schema'] != HERMES_HOST_READ_SCHEMA):
            raise FabricCompositionError('Hermes host observation differs from its closed schema')
        from common.hermes_role_status_contract import RoleStatusError, validate_source_pins
        from control_plane.remote_worker_transport import TransportValidationError, validate_host_ref
        from control_plane.fabric_remote_transport import FabricRemoteTransport
        try:
            validate_host_ref(value['host_ref'])
            validate_source_pins(value['expected_host_binding_sha256'], value['expected_implementation_sha'])
        except (RoleStatusError, TransportValidationError) as exc:
            raise FabricCompositionError('Hermes observation requires exact host and source pins') from exc
        return cls(value['host_ref'], FabricRemoteTransport.from_host_document(value['transport']),
                   value['expected_host_binding_sha256'], value['expected_implementation_sha'])



@dataclasses.dataclass(frozen=True)
class HermesSecretaryHostBinding:
    """One native conversation selected by the installed composition owner."""

    host_ref: str
    root_id: str
    root_job_id: str
    work_ref: str
    session_id: str
    profile_id: str
    principal_id: str
    transport: object
    expected_host_binding_sha256: str
    expected_implementation_sha: str

    @classmethod
    def _wire_schema(cls):
        if cls is HermesSecretaryHostBinding:
            return HERMES_SECRETARY_HOST_SCHEMA
        if cls is HermesMetaHostBinding:
            return HERMES_META_HOST_SCHEMA
        raise FabricCompositionError('Unsupported Hermes conversation binding class')

    @classmethod
    def from_document(cls, value):
        fields = {'schema', 'host_ref', 'root_id', 'root_job_id', 'work_ref', 'session_id',
                  'profile_id', 'principal_id', 'transport',
                  'expected_host_binding_sha256', 'expected_implementation_sha'}
        if (type(value) is not dict or set(value) != fields
                or value['schema'] != cls._wire_schema()):
            raise FabricCompositionError('Secretary selection differs from its closed schema')
        from control_plane.remote_worker_transport import (
            TransportValidationError, validate_secretary_native_id, validate_secretary_root_id,
        )
        try:
            validate_secretary_root_id(value['root_id'])
            validate_secretary_root_id(value['root_job_id'])
            for key in ('work_ref', 'session_id', 'profile_id', 'principal_id'):
                validate_secretary_native_id(value[key])
            from control_plane.workstream_admission_contract import canonical_work_ref
            canonical_work_ref(value['work_ref'])
            if re.fullmatch(r'JOB-[0-9]{1,9}', value['root_job_id']) is None:
                raise TransportValidationError('Secretary Runtime responsibility is invalid')
        except (TransportValidationError, ValueError):
            raise FabricCompositionError('Secretary selection identity is invalid') from None
        observation = HermesHostObservationBinding.from_document({
            'schema': HERMES_HOST_READ_SCHEMA,
            **{key: value[key] for key in ('host_ref', 'transport',
                    'expected_host_binding_sha256', 'expected_implementation_sha')},
        })
        return cls(value['host_ref'], value['root_id'], value['root_job_id'], value['work_ref'],
                   value['session_id'], value['profile_id'], value['principal_id'],
                   observation.transport, observation.expected_host_binding_sha256,
                   observation.expected_implementation_sha)

@dataclasses.dataclass(frozen=True)
class HermesMetaHostBinding(HermesSecretaryHostBinding):
    """The explicit Meta conversation, with its own installed native identity."""



def _remote_transports(values, bindings):
    index = {(b.host_ref, b.worker_id): b for b in bindings}
    from control_plane.fabric_remote_transport import FabricRemoteTransport
    transports = {}
    for value in values:
        if type(value) is not dict:
            raise FabricCompositionError('Remote Fabric transport is invalid')
        key = (value.get('host_ref'), value.get('worker_id'))
        if any(type(part) is not str for part in key) or key not in index or key in transports:
            raise FabricCompositionError('Remote Fabric transport requires one exact physical binding')
        transports[key] = FabricRemoteTransport.from_document(value, index[key])
    return MappingProxyType(transports)



@dataclasses.dataclass(frozen=True)
class NativeOperatorHostSelection:
    """Expected facts for the existing native Worker on the enrolled host.

    This slot grants no capability or account authority. Runtime and the original
    launch observation still compare the selected profile and actual process.
    """
    registration: object
    binding: object
    transport: object

    @classmethod
    def from_document(cls, value, observation):
        from control_plane.native_conversation_binding import NativeConversationRegistration
        from control_plane.operator_harness_wire import workspace_identity, OperatorHarnessWireError
        from control_plane.remote_attempt_transport import RemoteOperatorHostBinding, RemoteAttemptTransportError
        from integrations.deepseek_harness.operator_adapter import NativeOperatorAdapter, DSH_NATIVE_HARNESS_KIND
        fields = {'schema', 'registration', 'harness_binary_digest', 'harness_version',
                  'expected_config_digest', 'workspace'}
        registration_fields = {field.name for field in dataclasses.fields(NativeConversationRegistration)}
        if (type(value) is not dict or set(value) != fields
                or value['schema'] != NATIVE_OPERATOR_HOST_SCHEMA
                or type(value['registration']) is not dict
                or set(value['registration']) != registration_fields
                or any(type(item) is not str for item in value['registration'].values())
                or type(observation) is not HermesHostObservationBinding):
            raise FabricCompositionError('Native operator selection differs from its closed schema')
        try:
            registration = NativeConversationRegistration(**value['registration'])
            if registration.host_ref != observation.host_ref:
                raise ValueError('native selection differs from enrolled host')
            workspace = workspace_identity(value['workspace'])
            _absolute_path(workspace.workspace_path)
            if (workspace.workspace_path.startswith('//')
                    or type(workspace.base_sha) is not str
                    or re.fullmatch(r'[0-9a-f]{40}', workspace.base_sha) is None
                    or any(type(getattr(workspace, name)) is not int or getattr(workspace, name) < 0
                           for name in ('device', 'inode', 'uid', 'gid'))
                    or workspace.inode == 0):
                raise ValueError('native workspace identity is malformed')
            for name in ('harness_binary_digest', 'expected_config_digest'):
                if type(value[name]) is not str or _SHA256.fullmatch(value[name]) is None:
                    raise ValueError('native expected digest is malformed')
            binding = RemoteOperatorHostBinding(
                host_ref=registration.host_ref, worker_id=registration.worker_id,
                transport=observation.transport.binding,
                worker_source_config_digest=registration.worker_source_config_digest,
                provider='acp', harness_kind=DSH_NATIVE_HARNESS_KIND,
                harness_binary_digest=value['harness_binary_digest'],
                harness_version=value['harness_version'],
                expected_config_digest=value['expected_config_digest'], workspace=workspace,
                capabilities=NativeOperatorAdapter.describe_capabilities())
        except (TypeError, ValueError, OperatorHarnessWireError, RemoteAttemptTransportError) as exc:
            raise FabricCompositionError('Native operator expected host facts are invalid') from exc
        return cls(registration, binding, observation.transport)


def _composition_parts(raw):
    document = _document(raw)
    if type(document) is dict and document.get('schema_version') == NATIVE_CONFIG_SCHEMA_VERSION:
        expected = {'schema_version', 'bindings', 'remote_transports',
                    'hermes_role_metadata_read', 'hermes_secretary_conversation',
                    'hermes_meta_conversation', 'native_conversation'}
        if set(document) != expected:
            raise FabricCompositionError('Native composition differs from its closed schema')
        legacy = {key: value for key, value in document.items() if key != 'native_conversation'}
        legacy['schema_version'] = CONVERSATION_CONFIG_SCHEMA_VERSION
        bindings, transports, observation, secretary, meta, _ = _composition_parts(
            json.dumps(legacy, ensure_ascii=False, allow_nan=False).encode())
        native = NativeOperatorHostSelection.from_document(document['native_conversation'], observation)
        if any(binding.worker_id == native.registration.worker_id for binding in bindings):
            raise FabricCompositionError('Native operator cannot replace a Fabric Worker')
        return bindings, transports, observation, secretary, meta, native
    if type(document) is dict and document.get('schema_version') == CONVERSATION_CONFIG_SCHEMA_VERSION:
        expected = {'schema_version', 'bindings', 'remote_transports',
                    'hermes_role_metadata_read', 'hermes_secretary_conversation',
                    'hermes_meta_conversation'}
        if set(document) != expected:
            raise FabricCompositionError('Role conversation composition differs from its closed schema')
        meta = HermesMetaHostBinding.from_document(document['hermes_meta_conversation'])
        legacy = {key: value for key, value in document.items() if key != 'hermes_meta_conversation'}
        legacy['schema_version'] = SECRETARY_CONFIG_SCHEMA_VERSION
        bindings, transports, observation, secretary, _, _ = _composition_parts(
            json.dumps(legacy, ensure_ascii=False, allow_nan=False).encode())
        if (type(observation) is not HermesHostObservationBinding
                or meta.host_ref != observation.host_ref
                or meta.transport != observation.transport
                or meta.expected_host_binding_sha256 != observation.expected_host_binding_sha256
                or meta.expected_implementation_sha != observation.expected_implementation_sha):
            raise FabricCompositionError('Meta and observation require the same qualified host source')
        return bindings, transports, observation, secretary, meta, None
    if type(document) is dict and document.get('schema_version') == SECRETARY_CONFIG_SCHEMA_VERSION:
        expected = {'schema_version', 'bindings', 'remote_transports',
                    'hermes_role_metadata_read', 'hermes_secretary_conversation'}
        if set(document) != expected:
            raise FabricCompositionError('Secretary composition differs from its closed schema')
        secretary = HermesSecretaryHostBinding.from_document(document['hermes_secretary_conversation'])
        legacy = {key: value for key, value in document.items() if key != 'hermes_secretary_conversation'}
        legacy['schema_version'] = HOST_READ_CONFIG_SCHEMA_VERSION
        bindings, transports, observation, _, _, _ = _composition_parts(
            json.dumps(legacy, ensure_ascii=False, allow_nan=False).encode())
        if (type(observation) is not HermesHostObservationBinding
                or secretary.host_ref != observation.host_ref
                or secretary.transport != observation.transport
                or secretary.expected_host_binding_sha256 != observation.expected_host_binding_sha256
                or secretary.expected_implementation_sha != observation.expected_implementation_sha):
            raise FabricCompositionError('Secretary and observation require the same qualified host source')
        return bindings, transports, observation, secretary, None, None
    if type(document) is dict and document.get('schema_version') == HOST_READ_CONFIG_SCHEMA_VERSION:
        if (set(document) != {'schema_version', 'bindings', 'remote_transports', 'hermes_role_metadata_read'}
                or type(document['bindings']) is not list
                or type(document['remote_transports']) is not list):
            raise FabricCompositionError('Host-read Fabric composition differs from its closed schema')
        observation = HermesHostObservationBinding.from_document(document['hermes_role_metadata_read'])
        legacy = dict(schema_version=CONFIG_SCHEMA_VERSION, bindings=document['bindings'])
        bindings = (_bindings(json.dumps(legacy, ensure_ascii=False, allow_nan=False).encode())
                    if document['bindings'] else ())
        transports = _remote_transports(document['remote_transports'], bindings)
        if any(key[0] == observation.host_ref and transport.binding != observation.transport.binding
               for key, transport in transports.items()):
            raise FabricCompositionError('Conflicting transports for the same observation host are forbidden')
        return bindings, transports, observation, None, None, None
    if type(document) is dict and document.get('schema_version') == REMOTE_CONFIG_SCHEMA_VERSION:
        if (set(document) not in (
                    {'schema_version', 'bindings', 'remote_transports'},
                    {'schema_version', 'bindings', 'remote_transports', 'hermes_role_metadata_read'})
                or type(document['remote_transports']) is not list
                or not document['remote_transports']):
            raise FabricCompositionError('Remote Fabric composition differs from its closed schema')
        legacy = dict(schema_version=CONFIG_SCHEMA_VERSION, bindings=document['bindings'])
        bindings = _bindings(json.dumps(legacy, ensure_ascii=False, allow_nan=False).encode())
        transports = _remote_transports(document['remote_transports'], bindings)
        observation = None
        if 'hermes_role_metadata_read' in document:
            value = document['hermes_role_metadata_read']
            fields = {'host_ref', 'worker_id', 'expected_host_binding_sha256',
                      'expected_implementation_sha'}
            if type(value) is not dict or set(value) != fields:
                raise FabricCompositionError('Hermes observation selection differs from its closed schema')
            key = (value['host_ref'], value['worker_id'])
            if any(type(part) is not str for part in key) or key not in transports:
                raise FabricCompositionError('Hermes observation requires one exact installed remote transport')
            from common.hermes_role_status_contract import RoleStatusError, validate_source_pins
            try:
                validate_source_pins(value['expected_host_binding_sha256'],
                                     value['expected_implementation_sha'])
            except RoleStatusError as exc:
                raise FabricCompositionError('Hermes observation requires exact source pins') from exc
            observation = MappingProxyType(dict(value))
        return bindings, transports, observation, None, None, None
    return _bindings(raw), MappingProxyType({}), None, None, None, None

def _composition(raw):
    """Preserve the incumbent four-part validation interface for every version."""
    return _composition_parts(raw)[:4]


@dataclasses.dataclass(frozen=True)
class FabricBindingSource:
    """Callable exact-key lookup over one immutable approved composition file."""
    path: Path
    expected_sha256: str
    bindings: tuple[FabricHostBinding, ...]
    _file_identity: tuple[int, ...] = dataclasses.field(repr=False)
    _index: Mapping[tuple[str, str], FabricHostBinding] = dataclasses.field(repr=False, compare=False)
    _remote_index: Mapping = dataclasses.field(repr=False, compare=False)
    _hermes_role_metadata_read: Mapping | HermesHostObservationBinding | None = dataclasses.field(default=None, repr=False, compare=False)
    _hermes_secretary_conversation: HermesSecretaryHostBinding | None = dataclasses.field(default=None, repr=False, compare=False)
    _hermes_meta_conversation: HermesMetaHostBinding | None = dataclasses.field(default=None, repr=False, compare=False)
    _native_conversation: NativeOperatorHostSelection | None = dataclasses.field(default=None, repr=False, compare=False)

    @classmethod
    def from_path(cls, path: str | Path, expected_sha256: str) -> "FabricBindingSource":
        if type(expected_sha256) is not str or _SHA256.fullmatch(expected_sha256) is None:
            raise FabricCompositionError("Fabric composition requires an exact approved SHA-256")
        if not isinstance(path, (str, Path)):
            raise FabricCompositionError("Fabric composition requires a filesystem path")
        fixed_path = _absolute_path(str(path))
        raw, identity = _read_pinned(fixed_path, expected_sha256)
        bindings, remote_index, observation, secretary, meta, native = _composition_parts(raw)
        return cls(fixed_path, expected_sha256, bindings, identity,
                   MappingProxyType({(b.host_ref, b.worker_id): b for b in bindings}),
                   remote_index, observation, secretary, meta, native)

    def require_current(self) -> None:
        _, identity = _read_pinned(self.path, self.expected_sha256)
        if identity != self._file_identity:
            raise FabricCompositionError("Fabric composition file identity changed after pinning")

    @property
    def has_execution_bindings(self) -> bool:
        return bool(self.bindings or self._remote_index)

    @property
    def has_native_operator_binding(self) -> bool:
        return self._native_conversation is not None

    def native_conversation_selection(self) -> NativeOperatorHostSelection | None:
        self.require_current()
        selection = self._native_conversation
        if selection is not None:
            selection.transport.require_current()
        return selection

    def native_conversation_composition(self):
        from control_plane.native_conversation_binding import NativeConversationHostComposition
        selection = self.native_conversation_selection()
        if selection is None:
            return None
        def current():
            if self.native_conversation_selection() is not selection:
                raise FabricCompositionError('Native operator selection was replaced')
        return NativeConversationHostComposition(selection.registration, current, self.expected_sha256)

    def remote_operator_binding(self, host_ref: str, worker_id: str):
        selection = self.native_conversation_selection()
        if (selection is None or type(host_ref) is not str or type(worker_id) is not str
                or (host_ref, worker_id) != (selection.registration.host_ref, selection.registration.worker_id)):
            raise FabricCompositionError('Exact native operator host/worker is not installed')
        return selection.binding

    def __call__(self, host_ref: str, worker_id: str) -> FabricHostBinding:
        self.require_current()
        if type(host_ref) is not str or type(worker_id) is not str:
            raise FabricCompositionError("Fabric lookup requires exact host and worker strings")
        try:
            return self._index[(host_ref, worker_id)]
        except KeyError as exc:
            raise FabricCompositionError("Exact Fabric host/worker binding is not installed") from exc

    def hermes_secretary_selection(self) -> HermesSecretaryHostBinding | None:
        self.require_current()
        selection = self._hermes_secretary_conversation
        if selection is not None:
            selection.transport.require_current()
        return selection

    def hermes_secretary_client(self, *, root_id: str, session_id: str):
        """One exact installed conversation; no caller-selected endpoint or identity."""
        selection = self.hermes_secretary_selection()
        if selection is None:
            return None
        if root_id != selection.root_id or session_id != selection.session_id:
            raise FabricCompositionError('Secretary conversation is not the installed selection')
        return _PinnedSecretaryClient(self, selection)

    def hermes_meta_selection(self) -> HermesMetaHostBinding | None:
        self.require_current()
        selection = self._hermes_meta_conversation
        if selection is not None:
            selection.transport.require_current()
        return selection

    def hermes_meta_client(self, *, root_id: str, session_id: str):
        """The explicit Meta selection; an absent route never falls back."""
        selection = self.hermes_meta_selection()
        if selection is None:
            return None
        if root_id != selection.root_id or session_id != selection.session_id:
            raise FabricCompositionError('Meta conversation is not the installed selection')
        return _PinnedMetaClient(self, selection)

    def hermes_roles_reader(self):
        """Compose the fixed host read without admitting a Worker or Attempt."""
        selection = self._hermes_role_metadata_read
        if selection is None:
            return None
        if type(selection) is HermesHostObservationBinding:
            host_ref = selection.host_ref
            transport = selection.transport
            host_pin, implementation_pin = selection.expected_host_binding_sha256, selection.expected_implementation_sha
            physical = None
        else:
            key = (selection['host_ref'], selection['worker_id'])
            physical, transport = self._index[key], self._remote_index[key]
            host_ref = selection['host_ref']
            host_pin, implementation_pin = selection['expected_host_binding_sha256'], selection['expected_implementation_sha']

        def require_current():
            self.require_current()
            if physical is not None and self(*key) != physical:
                raise FabricCompositionError('Hermes observation route changed')
            transport.require_current()

        async def read():
            from common import workspace_byok_read_contract as wire
            from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
            try:
                require_current()
            except (FabricCompositionError, OSError):
                return wire.unavailable('SOURCE_CHANGED')
            try:
                client = RemoteWorkerBrokerClient.for_host_observation(
                    transport.binding, host_ref=host_ref,
                    expected_host_binding_sha256=host_pin,
                    expected_implementation_sha=implementation_pin)
                result = await client.read_hermes_roles()
            except Exception:
                result = wire.unavailable()
            try:
                require_current()
            except (FabricCompositionError, OSError):
                return wire.unavailable('SOURCE_CHANGED')
            return result

        return read

    def client_for(self, physical: FabricHostBinding, payload):
        if self(physical.host_ref, physical.worker_id) != physical:
            raise FabricCompositionError('Fabric client cannot change its installed physical route')
        remote = self._remote_index.get((physical.host_ref, physical.worker_id))
        if remote is None:
            from control_plane.executive_fabric_adapter import _fixed_client
            return _fixed_client(physical)
        from control_plane.fabric_remote_transport import PinnedFabricRemoteClient
        return PinnedFabricRemoteClient(self, physical, payload, remote)


class _PinnedConversationClient:
    """Currentness around the existing transport and its exact prewrite guard."""

    def __init__(self, source: FabricBindingSource, selection, *, role: str):
        from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
        if role == 'mmsecretary' and type(selection) is HermesSecretaryHostBinding:
            factory = RemoteWorkerBrokerClient.for_secretary_conversation
        elif role == 'mmmeta' and type(selection) is HermesMetaHostBinding:
            factory = RemoteWorkerBrokerClient.for_meta_conversation
        else:
            raise FabricCompositionError('Conversation client requires one exact role binding')
        self._source, self._selection, self._role = source, selection, role
        self._client = factory(
            selection.transport.binding, host_ref=selection.host_ref,
            root_id=selection.root_id, session_id=selection.session_id,
            expected_host_binding_sha256=selection.expected_host_binding_sha256,
            expected_implementation_sha=selection.expected_implementation_sha,
        )

    def _require_current(self):
        selected = (self._source.hermes_secretary_selection() if self._role == 'mmsecretary'
                    else self._source.hermes_meta_selection())
        if selected != self._selection:
            raise FabricCompositionError('Conversation selection changed')

    async def _request(self, request, *, before_write=None):
        from control_plane.remote_worker_transport import TransportEffect, TransportError
        code = 'secretary_binding_changed' if self._role == 'mmsecretary' else 'meta_binding_changed'
        modifying = type(request) is dict and request.get('operation') == 'submit'
        try:
            self._require_current()
        except Exception:
            raise TransportError(code, TransportEffect.NO_EFFECT) from None

        def guarded(operation, sealed_request):
            self._require_current()
            result = before_write(operation, sealed_request)
            self._require_current()
            return result

        send = (self._client.request_secretary if self._role == 'mmsecretary'
                else self._client.request_meta)
        result = await send(
            request, before_write=guarded if before_write is not None else None,
        )
        try:
            self._require_current()
        except Exception:
            raise TransportError(code,
                TransportEffect.EFFECT_UNKNOWN if modifying else TransportEffect.NO_EFFECT) from None
        return result


class _PinnedSecretaryClient(_PinnedConversationClient):
    def __init__(self, source: FabricBindingSource, selection: HermesSecretaryHostBinding):
        super().__init__(source, selection, role='mmsecretary')

    async def request_secretary(self, request, *, before_write=None):
        return await self._request(request, before_write=before_write)


class _PinnedMetaClient(_PinnedConversationClient):
    def __init__(self, source: FabricBindingSource, selection: HermesMetaHostBinding):
        super().__init__(source, selection, role='mmmeta')

    async def request_meta(self, request, *, before_write=None):
        return await self._request(request, before_write=before_write)
