"""Canonical paid qualification producer: source only, always disabled.

One default-disabled composition step for the occupied canonical-paid
definition. The root interval requalifies the installed v1 definition, the
selected release source map, the actual UID 501 bridge principal and the real
release manifest; then it owns exactly one opaque Bridge host qualification
(``qualify_paid_host`` + ``consume_paid_host_qualification``) and one private
Darwin RENAME_SWAP publication of the recomposed four artifacts. The canonical
``fabric-glm-paid-01`` definition directory is exchanged with one fixed
occupied staging sibling that is absent before any effect and retained after
the stage starts. Nothing here starts a listener or process, arms anything,
admits a Capacity worker, writes a credential or touches a Runtime row: a
successful return is still a disabled, offline, NOT_ADMITTED profile.

The raw ``transport_host`` argument is only a fixed-registry lookup key. The
canonical ``host_ref`` published in the v2 profile is derived exclusively from
the actually consumed observation's ``request.host_ref`` plus its
``transport_alias`` through the existing ``paid_host_reference`` owner, and the
held registry is re-read and rejoined after consumption. No raw observation
nonce, request preimage or capture-directory mtime is published. An uncertain
interval is sticky EFFECT_UNKNOWN with both directories retained; never
replayed, regenerated or cleaned up.
"""
from __future__ import annotations

import ctypes
import dataclasses
import fcntl
import os
import plistlib
import re
import stat
import sys
from pathlib import Path
from types import ModuleType

from ops.executive_os import autonomy_control as owner
from ops.executive_os import canonical_paid_definition as base
from ops.executive_os.capacity_broker_topology import CONTROL_UID
from control_plane.executive_host_pressure import HOST_REF_RE
from control_plane.paid_fabric_wire import PaidWireRefused, require_paid_source
from control_plane.paid_model_execution_contract import (
    PAID_REGISTRY_NAMESPACE,
    paid_host_reference,
)
from control_plane.paid_model_execution_contract import digest as _wire_digest
from control_plane.worker_execution_contract import BinaryAttestation

PROFILE_SCHEMA_V2 = 'mastermind.executive_paid_fabric_profile/v2'
BINDINGS_DOC_SCHEMA = 'mastermind.executive_paid_fabric_bindings/v1'
SOURCE_DOC_SCHEMA = 'mastermind.paid_worker_source/v1'
PHYSICAL_DOC_SCHEMA = 'mastermind.paid_fabric_host_binding/v1'
PAID_MODEL = 'glm-5.3-flash'
SELF_RELATIVE = 'ops/executive_os/canonical_paid_qualification.py'
QUALIFIER_EXT_RELATIVE = ('ops/native_fabric/quota_continuity/rollout/'
                          'native-code-stage/ext')
QUALIFIER_SOURCE_NAMES = frozenset({'host_pull.sh', 'host_pull_backend.py',
                                    'host_pull_probe.template',
                                    'paid_host_qualification.py',
                                    'remote_sub.sh'})
_REGISTRATION_FIELDS = frozenset({'worker_id', 'quota_class', 'account_label'})
_V2_FIELDS = base._PAID_PROFILE_FIELDS | {'registration', 'bindings_sha256'}
_BINARY_FIELDS = {field.name for field in dataclasses.fields(BinaryAttestation)}
_ID_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')
QUALIFIER_MODULE_NAME = 'paid_host_qualification.py'
_BRIDGE_PRINCIPAL_FIELDS = ('bridge_uid', 'bridge_gid', 'bridge_user',
                            'bridge_group', 'bridge_home')
# Fixed publication targets under the incumbent CONFIG_ROOT lock.
DESTINATION = Path(base.DESTINATION)
STAGING = DESTINATION.with_name(DESTINATION.name + '.initial-qualification')



class CanonicalPaidQualificationRefused(ValueError):
    """Closed, secret-free refusal before any qualification effect."""



class CanonicalPaidQualificationEffectUnknown(RuntimeError):
    """The stage started and the interval ended uncertainly; never replay."""



def _refuse(message, cause=None):
    raise CanonicalPaidQualificationRefused(message) from cause



def _production_entry_verified(expected_release_sha: str) -> None:
    """The real root production entry: UID 0, Darwin, isolated, pinned file."""
    pinned = (Path(owner.SYSTEM_ROOT) / 'releases' / expected_release_sha
              / SELF_RELATIVE)
    if (os.geteuid() != 0 or os.getuid() != 0 or sys.platform != 'darwin'
            or not sys.flags.isolated or not sys.flags.no_site
            or not sys.dont_write_bytecode
            or Path(__file__).absolute() != pinned):
        _refuse('root production entry identity required')



def _require_registration(worker_id, quota_class, account_label) -> dict:
    """Registration DATA only; never an admission, grant or Capacity proof."""
    if type(worker_id) is not str or worker_id != base.WORKER_ID:
        _refuse('canonical-paid worker identity is fixed')
    for value in (quota_class, account_label):
        if type(value) is not str or base._TOKEN_RE.fullmatch(value) is None:
            _refuse('canonical-paid registration DATA is not bounded')
    return {'worker_id': worker_id, 'quota_class': quota_class,
            'account_label': account_label}



def _require_transport_input(transport_host, python_path, capture_root) -> None:
    """Raw fixed-registry key plus requested transport paths; no canonical mapping."""
    if type(transport_host) is not str or _ID_RE.fullmatch(transport_host) is None:
        _refuse('raw transport registry key required')
    for value in (python_path, capture_root):
        if (type(value) is not str or not value.startswith('/') or len(value) > 4096
                or any(char in value for char in '\x00\r\n')
                or value != str(Path(value)) or '..' in Path(value).parts):
            _refuse('requested transport path is not a bounded absolute path')
    root = Path(capture_root)
    if root.name != 'lanes' or root.parent.name != 'ext' or str(root.parent.parent) == '/':
        _refuse('capture root is not a fixed lane ext/lanes directory')



def _require_staging_absent() -> None:
    try:
        os.lstat(STAGING)
    except FileNotFoundError:
        return
    except OSError as exc:
        _refuse('occupied staging sibling is unobservable', exc)
    _refuse('occupied staging sibling requires reconciliation')



def _require_paid_label_absent(host) -> None:
    if host._loaded_observe_only(base.PAID_LABEL):
        _refuse('canonical-paid service label is loaded')
    try:
        os.lstat(base.PAID_SOCKET_PATH)
    except FileNotFoundError:
        return
    except OSError as exc:
        _refuse('canonical-paid socket is unobservable', exc)
    _refuse('canonical-paid socket already exists')



def _read_definition_bytes(directory: Path) -> tuple[dict, tuple]:
    """Exact four-file root:wheel 0444 bundle inside one root:wheel 0755
    no-ACL no-symlink directory with no extra entries; bytes and identity only."""
    from control_plane.fs_security import has_macos_acl
    try:
        visible = directory.lstat()
    except OSError as exc:
        _refuse('canonical-paid definition directory is unavailable', exc)
    if (not stat.S_ISDIR(visible.st_mode) or (visible.st_uid, visible.st_gid) != (0, 0)
            or stat.S_IMODE(visible.st_mode) != 0o755
            or has_macos_acl(directory, expected_identity=visible)):
        _refuse('canonical-paid definition directory identity differs')
    try:
        names = set(os.listdir(directory))
    except OSError as exc:
        _refuse('canonical-paid definition is unreadable', exc)
    if names != set(base.FILES):
        _refuse('canonical-paid definition entries differ from the closed set')
    raw_files = {}
    for name in sorted(base.FILES):
        try:
            raw, _info = owner._read_root_file(directory / name,
                                               modes=frozenset({0o444}),
                                               uid=0, gid=0)
        except Exception as exc:
            _refuse('canonical-paid definition file is unavailable: ' + name, exc)
        raw_files[name] = raw
    return raw_files, (visible.st_dev, visible.st_ino)



def _read_occupied_definition() -> tuple[dict, tuple, dict, dict]:
    """The exact occupied v1 definition and root identity, all four artifacts
    revalidated through the unchanged v1 verifier so corruption (bridge config
    or launchd body included) refuses before qualification or staging."""
    raw_files, identity = _read_definition_bytes(DESTINATION)
    digests = {name: base.sha256(raw_files[name]) for name in sorted(base.FILES)}
    profile = base._document(raw_files['profile.json'])
    try:
        base.verify_candidate(raw_files)
        base._validate_paid_profile_document(profile)
    except base.CanonicalPaidPublicationRefused as exc:
        raise CanonicalPaidQualificationRefused(str(exc)) from exc
    except Exception as exc:
        _refuse('occupied canonical-paid definition is not the exact v1 source', exc)
    if profile['schema_version'] != base.PROFILE_SCHEMA:
        _refuse('canonical-paid definition is not the exact v1 inert source')
    if base._document(raw_files['bindings.json']) != {
            'schema_version': base.BINDINGS_SCHEMA_VERSION, 'bindings': []}:
        _refuse('occupied binding document is not the empty disabled source')
    return raw_files, identity, digests, profile



def _require_disarmed_configs(prior, expected_control_sha256) -> tuple[str, str]:
    """Exact Control preimage and both configs unchanged with every flag disarmed."""
    if prior.control_sha256 != expected_control_sha256:
        _refuse('Control source preimage changed')
    if any(prior.control.get(key, False) is not False
           for key in base._DISARMED_CONTROL_KEYS):
        _refuse('Control flags must remain disarmed')
    if prior.worker.get('operator_harness_armed') is not False:
        _refuse('primary Worker must remain disarmed')
    return prior.control_sha256, prior.worker_sha256



def _require_release_sources(release: Path, manifest: dict, verified: dict,
                             profile: dict) -> None:
    """Join the sealed source map, the raw pins and this fixed module file."""
    for name, relative in sorted(base.BOUND_SOURCE_PATHS.items()):
        original = base._manifest_entry(manifest['entries'], relative)
        observed = base._manifest_entry(verified['entries'], relative)
        if original != observed:
            _refuse('release source entry differs between manifest views: ' + relative)
        try:
            raw, _info = owner._read_root_file(release / relative,
                                               modes=base._RELEASE_SOURCE_MODES,
                                               uid=0, gid=0)
        except Exception as exc:
            _refuse('release source is unavailable: ' + relative, exc)
        if (len(raw) != original['size'] or base.sha256(raw) != original['sha256']
                or base.sha256(raw) != profile['source_digests'][name]):
            _refuse('release source differs from the sealed digest: ' + relative)
    for relative, (digest_value, size) in sorted(base.RAW_SOURCE_PINS.items()):
        original = base._manifest_entry(manifest['entries'], relative)
        observed = base._manifest_entry(verified['entries'], relative)
        if original != observed:
            _refuse('raw paid source entry differs between manifest views: ' + relative)
        try:
            raw, _info = owner._read_root_file(release / relative,
                                               modes=base._RELEASE_SOURCE_MODES,
                                               uid=0, gid=0)
        except Exception as exc:
            _refuse('raw paid source is unavailable: ' + relative, exc)
        if len(raw) != size or base.sha256(raw) != digest_value:
            _refuse('raw paid source differs from its immutable parent pin: ' + relative)
    relative = SELF_RELATIVE
    original = base._manifest_entry(manifest['entries'], relative)
    observed = base._manifest_entry(verified['entries'], relative)
    if original != observed:
        _refuse('fixed qualification module entry differs between manifest views')
    own = Path(__file__).read_bytes()
    if len(own) != original['size'] or base.sha256(own) != original['sha256']:
        _refuse('running qualification module differs from the installed release')



def _require_qualifier_sources(ext_dir: Path, manifest: dict,
                               verified: dict) -> dict[str, str]:
    """Five actual qualifier files: unique root-owned manifest entries and bytes."""
    expected = {}
    for name in sorted(QUALIFIER_SOURCE_NAMES):
        relative = QUALIFIER_EXT_RELATIVE + '/' + name
        original = base._manifest_entry(manifest['entries'], relative)
        observed = base._manifest_entry(verified['entries'], relative)
        if original != observed:
            _refuse('selected qualifier entry differs between manifest views: ' + name)
        try:
            raw, _info = owner._read_root_file(ext_dir / name,
                                               modes=base._RELEASE_SOURCE_MODES,
                                               uid=0, gid=0)
        except Exception as exc:
            _refuse('selected qualifier source is unavailable: ' + name, exc)
        if len(raw) != original['size'] or base.sha256(raw) != original['sha256']:
            _refuse('selected qualifier bytes differ from their manifest entry: ' + name)
        expected[name] = base.sha256(raw)
    return expected



def _load_qualifier(ext_dir: Path, verified_digest: str):
    """Load only digest-verified qualifier bytes as a private module: the
    root-owned file is read once, the expected digest gates every compile,
    exec and pycache use, and only the held verified bytes ever execute."""
    base._digest(verified_digest)
    location = ext_dir / QUALIFIER_MODULE_NAME
    try:
        raw, _info = owner._read_root_file(location,
                                           modes=base._RELEASE_SOURCE_MODES,
                                           uid=0, gid=0)
    except Exception as exc:
        _refuse('selected qualifier module is unavailable', exc)
    if base.sha256(raw) != verified_digest:
        _refuse('selected qualifier module bytes differ from the verified source')
    module = ModuleType('_canonical_paid_qualifier_bridge')
    module.__file__ = str(location)
    try:
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    except Exception as exc:
        _refuse('verified qualifier module did not load', exc)
    if (module.__file__ is None
            or Path(module.__file__).absolute() != Path(location).absolute()
            or frozenset(getattr(module, 'SOURCE_NAMES', ()))
            != QUALIFIER_SOURCE_NAMES):
        _refuse('loaded qualifier module is not the selected release source')
    return module



def _resolve_rename_swap():
    """Resolve the real Darwin SDK renameatx_np once, before any stage effect."""
    try:
        libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        swap = libc.renameatx_np
        swap.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                         ctypes.c_char_p, ctypes.c_uint]
        swap.restype = ctypes.c_int
    except (OSError, AttributeError) as exc:
        _refuse('Darwin RENAME_SWAP SDK support is unavailable', exc)
    return swap



def _paid_source_document(profile: dict, observation: dict,
                          registration: dict) -> tuple[dict, dict]:
    """The exact v1 wire source/physical pair from the sealed profile + observation."""
    request = observation['request']
    context = observation['context_identity']
    capture = observation['capture_identity']
    qualification = {
        'registry_key': request['host_ref'],
        'registry_sha256': request['registry_sha256'],
        'transport_alias': request['transport_alias'],
        'host_env_path': context['host_env_path'],
        'host_env_sha256': context['host_env_sha256'],
        'boot_id': observation['boot_id'],
        'capture_identity': {key: capture[key]
                             for key in ('device', 'inode', 'mode', 'uid', 'gid')},
        'qualifier_source_manifest_sha256': request['source_manifest_sha256'],
        'qualifier_sources_sha256': dict(request['sources_sha256']),
        'probe_sha256': request['probe_sha256'],
    }
    source = {
        'schema_version': SOURCE_DOC_SCHEMA,
        'worker_id': registration['worker_id'],
        'provider': 'glm', 'model': PAID_MODEL,
        'host_ref': profile['host_ref'],
        'worker_uid': observation['worker_uid'],
        'worker_gid': observation['worker_gid'],
        'worker_user': observation['worker_user'],
        'binary': dict(observation['binary']),
        'permission_profile_sha256': profile['permission_profile_sha256'],
        'execution_profile_digest': profile['execution_profile_sha256'],
        'service_source_sha256': profile['source_digests']['shim'],
        'bridge_uid': base.PAID_BRIDGE_UID,
        'socket_path': base.PAID_SOCKET_PATH,
        'capture_root': observation['capture_root'],
        'qualification': qualification,
        'capacity_capability_id': profile['capacity_capability_id'],
    }
    physical = {key: value for key, value in source.items()
                if key not in ('schema_version', 'capacity_capability_id')}
    physical['schema_version'] = PHYSICAL_DOC_SCHEMA
    physical['worker_source_config_digest'] = _wire_digest(source)
    return physical, source



def _expected_bridge_document() -> dict:
    return {
        'schema_version': base.CONFIG_SCHEMA, 'adapter_id': base.ADAPTER_ID,
        'bridge_uid': base.PAID_BRIDGE_UID, 'control_uid': CONTROL_UID,
        'launchd_socket_name': base.PAID_LAUNCHD_SOCKET_NAME,
        'socket_path': base.PAID_SOCKET_PATH,
        'workspace_root': base.PAID_WORKSPACE_ROOT, 'run_root': base.PAID_RUN_ROOT,
        'max_request_bytes': 1048576, 'max_response_bytes': 4194304,
        'request_timeout_seconds': 3600, 'validation_commands': [],
    }



def _v1_projection(profile: dict) -> dict:
    """Pure v1 projection for shared-constraint validation; DATA only, unpublished."""
    projection = {key: value for key, value in profile.items()
                  if key in base._PAID_PROFILE_FIELDS}
    projection['schema_version'] = base.PROFILE_SCHEMA
    projection['expected_remote_binary'] = None
    projection['remote_worker_identity'] = None
    return projection



def verify_qualified_artifacts(artifacts: dict) -> dict:
    """Pure closed-wire v2 verification: profile, hashes and one binding row.

    Validates the exact v2 schema version, registration DATA, the remote
    binary, the one-row bindings document through the pure
    ``require_paid_source`` owner, every host/registration/source/policy join,
    the fixed bridge config and the disabled launchd body, and revalidates
    shared v1 constraints on the pure v1 projection; the v1 verifier itself
    keeps refusing v2 and the projection is DATA only, never published."""
    if (type(artifacts) is not dict or set(artifacts) != set(base.FILES)
            or any(type(value) is not bytes or not 1 <= len(value) <= base.MAX_FILE_BYTES
                   for value in artifacts.values())):
        _refuse('four bounded exact source artifacts required')
    try:
        profile = base._document(artifacts['profile.json'])
        if type(profile) is not dict or set(profile) != set(_V2_FIELDS):
            _refuse('qualified profile differs from the closed v2 schema')
        if profile['schema_version'] != PROFILE_SCHEMA_V2:
            _refuse('qualified profile schema version differs from the exact v2 source')
        try:
            base._validate_paid_profile_document(_v1_projection(profile))
        except base.CanonicalPaidPublicationRefused as exc:
            raise CanonicalPaidQualificationRefused(str(exc)) from exc
        registration = profile['registration']
        if type(registration) is not dict or set(registration) != set(_REGISTRATION_FIELDS):
            _refuse('registration DATA differs from its closed schema')
        for key in ('worker_id', 'quota_class', 'account_label'):
            if (type(registration[key]) is not str
                    or base._TOKEN_RE.fullmatch(registration[key]) is None):
                _refuse('registration DATA is not bounded')
        if registration['worker_id'] != base.WORKER_ID:
            _refuse('registration worker identity differs from the fixed source')
        if (type(profile['bindings_sha256']) is not str
                or base._DIGEST_RE.fullmatch(profile['bindings_sha256']) is None
                or profile['bindings_sha256'] != base.sha256(artifacts['bindings.json'])):
            _refuse('bindings digest differs from the exact bindings bytes')
        if profile['bridge_armed'] is not False or profile['capacity_admitted'] is not False:
            _refuse('qualified profile must stay disarmed and unadmitted')
        if profile['model'] != PAID_MODEL:
            _refuse('qualified paid model is fixed')
        binary = profile['expected_remote_binary']
        if type(binary) is not dict or set(binary) != _BINARY_FIELDS:
            _refuse('remote binary differs from the exact attestation shape')
        if (type(binary['sha256']) is not str
                or base._DIGEST_RE.fullmatch(binary['sha256']) is None
                or any(type(binary[key]) is not int or binary[key] < 0
                       for key in ('size', 'device', 'inode', 'mode', 'uid', 'gid',
                                   'mtime_ns'))
                or binary['size'] <= 0 or not binary['mode'] & 0o111
                or type(binary['version']) is not str or not binary['version']
                or binary['team_identifier'] is not None):
            _refuse('remote binary attestation fields are not bounded actual data')
        BinaryAttestation(**binary)
        remote_identity = profile['remote_worker_identity']
        if (type(remote_identity) is not dict
                or set(remote_identity) != {'worker_uid', 'worker_gid', 'worker_user'}
                or any(type(remote_identity[key]) is not int or remote_identity[key] <= 0
                       for key in ('worker_uid', 'worker_gid'))
                or type(remote_identity['worker_user']) is not str
                or base._TOKEN_RE.fullmatch(remote_identity['worker_user']) is None):
            _refuse('remote worker identity differs from its exact shape')
        bridge = base._document(artifacts['bridge.json'])
        try:
            base._validate_paid_bridge_document(bridge)
        except base.CanonicalPaidPublicationRefused as exc:
            raise CanonicalPaidQualificationRefused(str(exc)) from exc
        if bridge != _expected_bridge_document():
            _refuse('bridge config differs from the fixed unchanged document')
        from control_plane.executive_fabric_bridge_broker import (
            BridgeConfig, BridgeProtocolError,
        )
        try:
            BridgeConfig.from_document(bridge)
        except BridgeProtocolError:
            pass
        else:
            _refuse('legacy bridge schema accepted the paid document')
        plist = plistlib.loads(artifacts[base.PAID_LABEL + '.plist'])
        if plist != base._expected_plist(_v1_projection(profile)):
            _refuse('launchd body differs from the fixed disabled profile')
        if (plist.get('Disabled') is not True or plist.get('RunAtLoad') is not False
                or plist.get('KeepAlive') is not False):
            _refuse('qualified definition must ship disabled')
        bindings = base._document(artifacts['bindings.json'])
        if (type(bindings) is not dict
                or set(bindings) != {'schema_version', 'bindings'}
                or bindings['schema_version'] != BINDINGS_DOC_SCHEMA
                or type(bindings['bindings']) is not list
                or len(bindings['bindings']) != 1):
            _refuse('bindings document differs from its closed one-row schema')
        row = bindings['bindings'][0]
        if type(row) is not dict or set(row) != {'physical_binding', 'source_config',
                                                 'quota_class'}:
            _refuse('binding row differs from its closed schema')
        physical, source = row['physical_binding'], row['source_config']
        if type(physical) is not dict or type(source) is not dict:
            _refuse('binding row documents are not exact objects')
        try:
            require_paid_source(physical, source)
        except PaidWireRefused as exc:
            raise CanonicalPaidQualificationRefused(
                'paid source wire validation refused') from exc
        if (row['quota_class'] != registration['quota_class']
                or physical['worker_id'] != profile['worker_id']
                or source['worker_id'] != registration['worker_id']
                or physical['host_ref'] != profile['host_ref']
                or source['host_ref'] != profile['host_ref']):
            _refuse('binding/profile identity join differs')
        if (source['permission_profile_sha256'] != profile['permission_profile_sha256']
                or source['execution_profile_digest'] != profile['execution_profile_sha256']
                or source['provider'] != profile['provider']
                or source['model'] != profile['model']):
            _refuse('binding/profile policy join differs')
        qualification = source['qualification']
        if paid_host_reference(qualification['registry_key'],
                               qualification['transport_alias']) != profile['host_ref']:
            _refuse('canonical host reference differs from its consumed registry join')
        if (source['binary'] != binary
                or {'worker_uid': source['worker_uid'], 'worker_gid': source['worker_gid'],
                    'worker_user': source['worker_user']} != remote_identity
                or source['service_source_sha256'] != profile['source_digests']['shim']
                or source['socket_path'] != profile['socket_path']
                or source['socket_path'] != base.PAID_SOCKET_PATH
                or source['bridge_uid'] != base.PAID_BRIDGE_UID
                or profile['bridge_uid'] != base.PAID_BRIDGE_UID
                or source['capacity_capability_id'] != profile['capacity_capability_id']):
            _refuse('binding/profile source join differs')
        hashes = {name: base.sha256(artifacts[name]) for name in sorted(base.FILES)}
    except CanonicalPaidQualificationRefused:
        raise
    except Exception as exc:
        _refuse('qualified artifact validation refused', exc)
    return {'profile': profile, 'hashes': hashes, 'bindings': [dict(row)]}



def _rejoin_registry(qualifier, request: dict) -> str:
    """Root re-read of the same fixed registry; rederive the canonical host ref."""
    try:
        raw, _identity = qualifier._read_owned(PAID_REGISTRY_NAMESPACE,
                                               owners={0, base.PAID_BRIDGE_UID})
        registry = qualifier._json(raw)
    except Exception as exc:
        _refuse('fixed registry rejoin failed', exc)
    if base.sha256(raw) != request['registry_sha256']:
        _refuse('fixed registry changed after qualification')
    entry = registry.get(request['host_ref']) if type(registry) is dict else None
    if type(entry) is not dict or entry.get('ssh_alias') != request['transport_alias']:
        _refuse('transport alias differs from the consumed registry entry')
    return paid_host_reference(request['host_ref'], request['transport_alias'])



def _recheck_held_context(host, *, expected_release_sha, control_sha256,
                          worker_sha256, lock_fd, expected_sources, ext_dir,
                          manifest_sha256, staging_absent=True) -> None:
    """Every joined external identity except the definition bundle itself:
    install, transaction, services, UIDs, Runtime, disarm, held root, label,
    manifest, qualifier sources. Shared by pre-stage and post-swap."""
    host.require_exact_install(expected_release_sha)
    host.require_transaction_absent()
    host.require_services_already_stopped()
    host.require_service_uids_quiescent()
    current = host.load_unarmed_configs(expected_release_sha)
    host.require_runtime_quiescent(current)
    if (current.control_sha256 != control_sha256
            or current.worker_sha256 != worker_sha256):
        _refuse('original config postimage changed')
    _require_disarmed_configs(current, control_sha256)
    host._config_root_safe()
    base._trusted_control_root(lock_fd)
    held, visible = os.fstat(lock_fd), Path(owner.CONFIG_ROOT).lstat()
    if (held.st_dev, held.st_ino) != (visible.st_dev, visible.st_ino):
        _refuse('incumbent config root moved')
    if staging_absent:
        _require_staging_absent()
    _require_paid_label_absent(host)
    try:
        raw_manifest = owner._release_manifest_bytes(expected_release_sha)
    except Exception as exc:
        _refuse('installed release manifest is unavailable', exc)
    if base.sha256(raw_manifest) != manifest_sha256:
        _refuse('installed release manifest changed under qualification')
    for name in sorted(expected_sources):
        try:
            raw, _info = owner._read_root_file(ext_dir / name,
                                               modes=base._RELEASE_SOURCE_MODES,
                                               uid=0, gid=0)
        except Exception as exc:
            _refuse('selected qualifier source is unavailable: ' + name, exc)
        if base.sha256(raw) != expected_sources[name]:
            _refuse('selected qualifier source changed under qualification')



def _recheck_context(host, *, expected_release_sha, control_sha256, worker_sha256,
                     lock_fd, original_identity, original_digests,
                     expected_sources, ext_dir, manifest_sha256,
                     staging_absent=True) -> None:
    """Immediately-before-effect requalification of every joined identity."""
    _recheck_held_context(host, expected_release_sha=expected_release_sha,
                          control_sha256=control_sha256,
                          worker_sha256=worker_sha256, lock_fd=lock_fd,
                          expected_sources=expected_sources, ext_dir=ext_dir,
                          manifest_sha256=manifest_sha256,
                          staging_absent=staging_absent)
    _current_bytes, current_identity, current_digests, _profile = (
        _read_occupied_definition())
    if current_identity != original_identity or current_digests != original_digests:
        _refuse('canonical-paid definition changed under qualification')



def _stage_target(target: dict[str, bytes]) -> None:
    """Exclusive retained 0700 sibling; exact four root:wheel 0444 artifacts."""
    os.mkdir(STAGING, 0o700)
    os.chown(STAGING, 0, 0)
    for name in sorted(base.FILES):
        owner._atomic_file(STAGING / name, target[name], mode=0o444,
                           uid=0, gid=0, replace=False)
    os.chmod(STAGING, 0o755, follow_symlinks=False)
    owner._fsync_directory(STAGING)
    owner._fsync_directory(owner.CONFIG_ROOT)



def _verify_staged(target: dict[str, bytes]) -> tuple[int, int]:
    from control_plane.fs_security import has_macos_acl
    visible = STAGING.lstat()
    if ((visible.st_uid, visible.st_gid, stat.S_IMODE(visible.st_mode)) != (0, 0, 0o755)
            or has_macos_acl(STAGING, expected_identity=visible)
            or set(os.listdir(STAGING)) != set(base.FILES)):
        raise CanonicalPaidQualificationEffectUnknown('staged directory identity differs')
    for name in sorted(base.FILES):
        try:
            raw, _info = owner._read_root_file(STAGING / name,
                                               modes=frozenset({0o444}), uid=0, gid=0)
        except Exception as exc:
            raise CanonicalPaidQualificationEffectUnknown(
                'staged artifact is unreadable') from exc
        if raw != target[name]:
            raise CanonicalPaidQualificationEffectUnknown('staged artifact bytes differ')
    return visible.st_dev, visible.st_ino



def _verify_exchange_generations(staged_identity: tuple, target: dict[str, bytes],
                                 original_identity: tuple,
                                 original_digests: dict) -> None:
    """Both generations re-verified immediately before the rename syscall: a
    moved or substituted staging sibling refuses before the exchange can
    publish unverified bytes; no rename ctime is ever compared."""
    try:
        visible, current = os.lstat(STAGING), os.lstat(DESTINATION)
    except OSError as exc:
        raise CanonicalPaidQualificationEffectUnknown(
            'exchange generation is unobservable before the swap') from exc
    if (visible.st_dev, visible.st_ino) != staged_identity:
        raise CanonicalPaidQualificationEffectUnknown(
            'staged directory moved before the exchange')
    if (current.st_dev, current.st_ino) != original_identity:
        raise CanonicalPaidQualificationEffectUnknown(
            'original definition moved before the exchange')
    original_bytes, _identity = _read_definition_bytes(DESTINATION)
    if {name: base.sha256(original_bytes[name])
            for name in sorted(base.FILES)} != original_digests:
        raise CanonicalPaidQualificationEffectUnknown(
            'original definition generation differs before the exchange')
    for name in sorted(base.FILES):
        try:
            raw, _info = owner._read_root_file(STAGING / name,
                                               modes=frozenset({0o444}), uid=0, gid=0)
            if raw != target[name]:
                raise ValueError('staged bytes differ before the exchange')
        except Exception as exc:
            raise CanonicalPaidQualificationEffectUnknown(str(exc)) from exc



def _verify_postimage(staged_identity: tuple, original_identity: tuple,
                      original_bytes: dict, target: dict[str, bytes], *, host,
                      expected_release_sha, control_sha256, worker_sha256,
                      lock_fd, expected_sources, ext_dir, manifest_sha256,
                      expected_hashes: dict) -> dict:
    """Final whole-context check of the exchanged canonical definition: the
    target keeps the staged inode and exact v2 bytes, the archive the original
    generation, every joined external identity holds, and the pure v2
    verifier re-validates the actual published bytes."""
    destination, archive = os.lstat(DESTINATION), os.lstat(STAGING)
    if ((destination.st_dev, destination.st_ino) != staged_identity
            or (archive.st_dev, archive.st_ino) != original_identity):
        raise CanonicalPaidQualificationEffectUnknown('exchanged inode unconfirmed')
    published_bytes, _identity = _read_definition_bytes(DESTINATION)
    archived_bytes, _identity = _read_definition_bytes(STAGING)
    if published_bytes != target or archived_bytes != original_bytes:
        raise CanonicalPaidQualificationEffectUnknown('exchanged bytes unconfirmed')
    _recheck_held_context(host, expected_release_sha=expected_release_sha,
                          control_sha256=control_sha256,
                          worker_sha256=worker_sha256, lock_fd=lock_fd,
                          expected_sources=expected_sources, ext_dir=ext_dir,
                          manifest_sha256=manifest_sha256,
                          staging_absent=False)
    verified = verify_qualified_artifacts(published_bytes)
    if verified['hashes'] != expected_hashes:
        raise CanonicalPaidQualificationEffectUnknown(
            'published artifacts lost their qualified identity')
    return verified



def qualify_and_publish(expected_release_sha: str,
                        expected_control_sha256: str,
                        expected_definition_sha256: str, *,
                        transport_host, python_path, capture_root, worker_id,
                        quota_class, account_label) -> dict[str, object]:
    """One root-owner disabled qualification and fixed-target RENAME_SWAP.

    Every input, principal, release, source, manifest, registry and service
    qualification happens before the opaque Bridge qualification, and the
    whole context is rechecked immediately before the swap. The Bridge
    producer is called exactly once and consumed exactly once inside the held
    CONFIG_ROOT interval; its opaque same-process result is never replaced by
    caller data. Joins are rechecked after staging, both generations right
    before the syscall, and the full published/archived/external context
    after the exchange; later uncertainty stays sticky EFFECT_UNKNOWN.
    """
    # Exact caller identity syntax before any path or gate is built.
    try:
        base._commit(expected_release_sha)
        base._digest(expected_control_sha256)
        base._digest(expected_definition_sha256)
    except base.CanonicalPaidPublicationRefused as exc:
        raise CanonicalPaidQualificationRefused(str(exc)) from exc
    _production_entry_verified(expected_release_sha)
    registration = _require_registration(worker_id, quota_class, account_label)
    _require_transport_input(transport_host, python_path, capture_root)
    host = owner.ProductionCeoSubmitHost()
    lock_fd = -1
    effect = False
    try:
        host.require_exact_install(expected_release_sha)
        host.require_transaction_absent()
        host._config_root_safe()
        lock_fd = os.open(owner.CONFIG_ROOT,
                          os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0)
                          | getattr(os, 'O_CLOEXEC', 0))
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CanonicalPaidQualificationRefused(
                'incumbent Control publication mutex occupied') from exc
        base._trusted_control_root(lock_fd)
        _require_staging_absent()
        swap = _resolve_rename_swap()
        prior = host.load_unarmed_configs(expected_release_sha)
        host.require_runtime_quiescent(prior)
        control_sha256, worker_sha256 = _require_disarmed_configs(
            prior, expected_control_sha256)
        host.require_services_already_stopped()
        host.require_service_uids_quiescent()
        _require_paid_label_absent(host)
        original_bytes, original_identity, original_digests, profile = (
            _read_occupied_definition())
        aggregate = _wire_digest(original_digests)
        if aggregate != expected_definition_sha256:
            _refuse('stale canonical-paid definition preimage')
        if profile['release_commit'] != expected_release_sha:
            _refuse('occupied profile binds a different protected release')
        if profile['model'] != PAID_MODEL:
            _refuse('occupied profile model differs from the fixed paid model')
        principal = base._qualify_bridge_principal()
        if any(profile[key] != principal[key] for key in _BRIDGE_PRINCIPAL_FIELDS):
            _refuse('actual bridge principal differs from the sealed profile')
        release = Path(owner.SYSTEM_ROOT) / 'releases' / expected_release_sha
        manifest_raw = owner._release_manifest_bytes(expected_release_sha)
        manifest = base._document(manifest_raw)
        if type(manifest) is not dict or manifest.get('commit_sha') != expected_release_sha:
            _refuse('installed release manifest differs')
        tree = base._commit(manifest.get('tree_sha'))
        manifest_sha256 = base.sha256(manifest_raw)
        if tree != profile['release_tree']:
            _refuse('installed release tree differs from the sealed profile')
        if manifest_sha256 != profile['release_manifest_sha256']:
            _refuse('installed release manifest differs from the sealed profile')
        from ops.executive_os.release_manifest import verify
        verified = verify(release, expected_release_sha, tree)
        if type(verified) is not dict or type(verified.get('entries')) is not list:
            _refuse('installed release verification is unavailable')
        _require_release_sources(release, manifest, verified, profile)
        ext_dir = release / QUALIFIER_EXT_RELATIVE
        expected_sources = _require_qualifier_sources(ext_dir, manifest, verified)
        qualifier = _load_qualifier(ext_dir,
                                    expected_sources[QUALIFIER_MODULE_NAME])
        _recheck_context(host, expected_release_sha=expected_release_sha,
                         control_sha256=control_sha256,
                         worker_sha256=worker_sha256, lock_fd=lock_fd,
                         original_identity=original_identity,
                         original_digests=original_digests,
                         expected_sources=expected_sources, ext_dir=ext_dir,
                         manifest_sha256=manifest_sha256)
        binding = dict(host_ref=transport_host, hosts_path=PAID_REGISTRY_NAMESPACE,
                       release_sha=expected_release_sha,
                       source_manifest_sha256=manifest_sha256,
                       preimage_sha256=expected_definition_sha256,
                       expected_sources=dict(expected_sources))
        observed = qualifier.qualify_paid_host(python_path=python_path,
                                               capture_root=capture_root, **binding)
        observation = qualifier.consume_paid_host_qualification(observed, **binding)
        request = observation['request']
        canonical_host_ref = _rejoin_registry(qualifier, request)
        if HOST_REF_RE.fullmatch(canonical_host_ref) is None:
            _refuse('derived canonical host reference differs from its owner syntax')
        if request['host_ref'] != transport_host:
            _refuse('consumed observation registry key differs from the raw key')
        composed = dict(profile)
        composed['schema_version'] = PROFILE_SCHEMA_V2
        composed['host_ref'] = canonical_host_ref
        composed['expected_remote_binary'] = dict(observation['binary'])
        composed['remote_worker_identity'] = {
            'worker_uid': observation['worker_uid'],
            'worker_gid': observation['worker_gid'],
            'worker_user': observation['worker_user'],
        }
        composed['registration'] = dict(registration)
        physical, source = _paid_source_document(composed, observation, registration)
        row = {'physical_binding': physical, 'source_config': source,
               'quota_class': registration['quota_class']}
        bindings_bytes = base._json({'schema_version': BINDINGS_DOC_SCHEMA,
                                     'bindings': [row]})
        composed['bindings_sha256'] = base.sha256(bindings_bytes)
        target = {'profile.json': base._json(composed),
                  'bridge.json': original_bytes['bridge.json'],
                  'bindings.json': bindings_bytes,
                  base.PAID_LABEL + '.plist': original_bytes[base.PAID_LABEL + '.plist']}
        verified_artifacts = verify_qualified_artifacts(target)
        try:
            raw, _identity = qualifier._read_owned(PAID_REGISTRY_NAMESPACE,
                                                   owners={0, base.PAID_BRIDGE_UID})
        except Exception as exc:
            _refuse('fixed registry pre-effect rejoin failed', exc)
        if base.sha256(raw) != request['registry_sha256']:
            _refuse('fixed registry changed before publication')
        _recheck_context(host, expected_release_sha=expected_release_sha,
                         control_sha256=control_sha256,
                         worker_sha256=worker_sha256, lock_fd=lock_fd,
                         original_identity=original_identity,
                         original_digests=original_digests,
                         expected_sources=expected_sources, ext_dir=ext_dir,
                         manifest_sha256=manifest_sha256)
        effect = True
        _stage_target(target)
        staged_identity = _verify_staged(target)
        _recheck_context(host, expected_release_sha=expected_release_sha,
                         control_sha256=control_sha256,
                         worker_sha256=worker_sha256, lock_fd=lock_fd,
                         original_identity=original_identity,
                         original_digests=original_digests,
                         expected_sources=expected_sources, ext_dir=ext_dir,
                         manifest_sha256=manifest_sha256,
                         staging_absent=False)
        if any(composed[key] != base._qualify_bridge_principal()[key]
               for key in _BRIDGE_PRINCIPAL_FIELDS):
            _refuse('actual bridge principal changed before publication')
        if _rejoin_registry(qualifier, request) != canonical_host_ref:
            _refuse('fixed registry changed before publication')
        _verify_exchange_generations(staged_identity, target, original_identity,
                                     original_digests)
        ctypes.set_errno(0)
        if swap(lock_fd, os.fsencode(STAGING.name), lock_fd,
                os.fsencode(DESTINATION.name), 0x2) != 0:
            raise CanonicalPaidQualificationEffectUnknown(
                'original paid definition exchange failed')
        os.fsync(lock_fd)
        post = _verify_postimage(staged_identity, original_identity,
                                 original_bytes, target, host=host,
                                 expected_release_sha=expected_release_sha,
                                 control_sha256=control_sha256,
                                 worker_sha256=worker_sha256, lock_fd=lock_fd,
                                 expected_sources=expected_sources,
                                 ext_dir=ext_dir,
                                 manifest_sha256=manifest_sha256,
                                 expected_hashes=verified_artifacts['hashes'])
        _require_release_sources(release, manifest, verified, profile)
        if any(post['profile'][key] != base._qualify_bridge_principal()[key]
               for key in _BRIDGE_PRINCIPAL_FIELDS):
            raise CanonicalPaidQualificationEffectUnknown(
                'actual bridge principal changed during publication')
        if _rejoin_registry(qualifier, request) != canonical_host_ref:
            raise CanonicalPaidQualificationEffectUnknown(
                'fixed registry changed during publication')
        return {'state': 'PAID_PROFILE_QUALIFIED_DISABLED', 'effect': 'APPLIED',
                'release': expected_release_sha,
                'control_preimage_sha256': expected_control_sha256,
                'definition_preimage_sha256': expected_definition_sha256,
                'artifacts': verified_artifacts['hashes'],
                'admitted_worker': False, 'capacity_admitted': False,
                'bridge_armed': False, 'service_started': False,
                'readiness': 'OFFLINE_NOT_ADMITTED',
                'identity_reference': {
                    'bindings_path': str(DESTINATION / 'bindings.json'),
                    'bindings_sha256': composed['bindings_sha256']}}
    except CanonicalPaidQualificationRefused as exc:
        if effect:
            raise CanonicalPaidQualificationEffectUnknown(
                'original paid qualification effect unconfirmed') from exc
        raise
    except CanonicalPaidQualificationEffectUnknown:
        raise
    except Exception as exc:
        if effect:
            raise CanonicalPaidQualificationEffectUnknown(
                'original paid qualification effect unconfirmed') from exc
        raise CanonicalPaidQualificationRefused(
            'original paid qualification context refused') from exc
    finally:
        if lock_fd >= 0:
            try:
                os.close(lock_fd)
            except OSError:
                pass
