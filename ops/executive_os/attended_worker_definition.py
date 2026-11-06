"""Render one secondary attended worker using existing protected schemas.

No principal allocation, secret enrollment, publication, activation or admission.
The host owner supplies actual selected resources; output is inert installation
input. The primary Codex worker and sealed release contents remain untouched.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
import plistlib
import re

from control_plane import executive_fabric_bridge_broker as bridge
from control_plane import fabric_attended_canary as canary
from control_plane.executive_fabric_adapter import FabricHostBinding
from control_plane.executive_fabric_composition import CONFIG_SCHEMA_VERSION, _bindings
from control_plane.fabric_attended_claude import (
    MAX_TURNS_LIMIT, _reviewed_binary, _reviewed_binding_and_profile, _reviewed_model,
    finite_read_permission_digest,
)
from control_plane.subscription_catalog import get_binding
from control_plane.subscription_provider_profiles import get_profile
from control_plane.worker_execution_contract import BinaryAttestation


class AttendedDefinitionError(ValueError):
    pass


def _path(value):
    path = Path(value)
    if (not path.is_absolute() or '..' in path.parts or str(path) != str(value)
            or any(ord(c) < 32 for c in str(path))):
        raise AttendedDefinitionError('canonical absolute path required')
    return path


def _identifier(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.:-]{0,127}', value) is None:
        raise AttendedDefinitionError('bounded installation identity required')
    return value


def _sha(value, length=64):
    if type(value) is not str or re.fullmatch('[0-9a-f]{%d}' % length, value) is None:
        raise AttendedDefinitionError('exact source digest required')
    return value


def _json(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def attest_binary_document(path, *, allowed_versions):
    """Host-owner operation: observe the executable with the existing attester.

    This returns bytes for later protected publication. It does not install a
    receipt, substitute caller-supplied claims, or read a credential.
    """
    from control_plane.claude_subscription_worker import attest_claude_binary
    from control_plane.codex_provider_realm import _native_open
    from control_plane.codex_worker import _assert_binary_unchanged
    path = _path(path)
    versions = frozenset(allowed_versions)
    if not 1 <= len(versions) <= 4 or any(type(v) is not str or not v or len(v) > 64 for v in versions):
        raise AttendedDefinitionError('small exact version allowlist required')
    with _native_open(path):
        binary = attest_claude_binary(path, allowed_versions=versions)
        _reviewed_binary(binary)
        if binary.uid != 0 or binary.path != binary.real_path:
            raise AttendedDefinitionError('canonical root-owned binary required')
        _assert_binary_unchanged(binary)
    return _json({'schema_version': 'mastermind.attended_claude_binary/v1',
                  'binary': dataclasses.asdict(binary)})


def build_finite_control_delta(*, definition_dir, worker_artifacts, native_capacity_v2=None):
    """Pure staging delta for the existing root-owned Control publisher.

    No arm/submit flag, activation receipt, quota or service is produced here.
    The existing autonomy owner later derives foreground-only armed bytes and
    binds them in its original transaction. Host publication supplies the real
    installed artifacts, never placeholder release/binary/realm digests.
    """
    from control_plane.executive_fabric_composition import _document
    from control_plane.fabric_attended_routing import FINITE_DEFINITION_DIR, FINITE_SOCKET_PATH
    directory = _path(definition_dir)
    if str(directory) != FINITE_DEFINITION_DIR:
        raise AttendedDefinitionError('finite Control requires its fixed definition directory')
    try:
        worker_bytes = worker_artifacts['worker.json']
        bindings_bytes = worker_artifacts['bindings.json']
        worker = _document(worker_bytes)
        physical, = _bindings(bindings_bytes)
    except (KeyError, TypeError, ValueError) as exc:
        raise AttendedDefinitionError('one complete rendered finite owner required') from exc
    if (worker.get('worker_id') != 'minimax-finite-01'
            or physical.worker_id != worker['worker_id'] or physical.provider != 'minimax'
            or physical.socket_path != FINITE_SOCKET_PATH
            or physical.worker_source_config_digest != _digest(worker_bytes)
            or worker.get('harness_binding_id') != canary.BINDING):
        raise AttendedDefinitionError('finite Control delta differs from its original worker')
    value = dict(fabric_bridge_armed=False, fabric_bindings_path=str(directory/'bindings.json'),
        fabric_bindings_sha256=_digest(bindings_bytes),
        fabric_attended_probe={'worker_config_path': str(directory/'worker.json')})
    if native_capacity_v2 is not None:
        from ops.executive_os.capacity_source_contract import validate_native_subscription_capacity_enrollment
        from scripts.executive_os_phase1c import _validate_fabric_bridge_config, ServiceError
        enrollment = validate_native_subscription_capacity_enrollment(
            worker.get('native_capacity_enrollment'))
        if (type(native_capacity_v2) is not dict
                or native_capacity_v2.get('macro_release') != enrollment['registration_source']['release_commit']):
            raise AttendedDefinitionError('native Control source differs from its worker')
        value['native_capacity_v2'] = dict(native_capacity_v2)
        try:
            _validate_fabric_bridge_config(value)
        except ServiceError:
            raise AttendedDefinitionError('native Control source pin is invalid') from None
    return value


def _entry(release_root, commit_sha, tree_sha, manifest_sha256, arguments):
    # Root-installed generated entry is OUTSIDE the sealed release. Only a
    # literal exact release is importable under -I -S; argv/env select nothing.
    return ('''"""Fixed host-owner composition; no runtime selectors."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

def protected(path, directory=False):
    for item in (path, *path.parents):
        info = item.lstat()
        is_dir = directory or item != path
        if (info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISDIR(info.st_mode) if is_dir else stat.S_ISREG(info.st_mode))):
            raise RuntimeError("untrusted installation source")

def main():
    if len(sys.argv) != 1:
        raise RuntimeError("fixed entry takes no arguments")
    protected(Path(__file__).absolute())
    release = Path(RELEASE)
    protected(release, directory=True)
    manifest = release / ".executive-release-manifest.json"
    protected(manifest)
    manifest_bytes = manifest.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST:
        raise RuntimeError("release manifest changed")
    document = json.loads(manifest_bytes)
    if document.get("commit_sha") != COMMIT or document.get("tree_sha") != TREE:
        raise RuntimeError("release identity changed")
    rows = {row["path"]: row for row in document["entries"]}
    # Bootstrap the EXISTING stdlib-only ACL observer from held, pinned bytes.
    # Importing its package first could execute changed __init__ code before
    # release verification, so no release import occurs in this step.
    acl_path = release / "control_plane/fs_security.py"
    protected(acl_path)
    acl_bytes = acl_path.read_bytes()
    if hashlib.sha256(acl_bytes).hexdigest() != rows["control_plane/fs_security.py"]["sha256"]:
        raise RuntimeError("ACL observer changed")
    acl_scope = {"__name__": "_fixed_attended_acl_bootstrap", "__file__": str(acl_path)}
    exec(compile(acl_bytes, str(acl_path), "exec"), acl_scope)
    has_acl = acl_scope["has_macos_acl"]
    entry = Path(__file__).absolute()
    for path in (entry, *entry.parents, release, *release.parents, manifest):
        if has_acl(path, expected_identity=path.lstat()):
            raise RuntimeError("untrusted installation ACL")
    # Before importing any release package, check its entire declared content
    # and refuse extra paths. Full canonical verification follows through the
    # incumbent verifier; this bootstrap grants no release or launch authority.
    seen = set()
    for directory, names, files in os.walk(release, followlinks=False):
        for name in names + files:
            path = Path(directory) / name
            relative = path.relative_to(release).as_posix()
            if relative == ".executive-release-manifest.json":
                continue
            row = rows[relative]
            info = path.lstat()
            if (info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022
                    or has_acl(path, expected_identity=info, allow_symlink=stat.S_ISLNK(info.st_mode))):
                raise RuntimeError("untrusted release object")
            if stat.S_IMODE(info.st_mode) != row["mode"]:
                raise RuntimeError("release mode changed")
            if row["type"] == "file":
                if not stat.S_ISREG(info.st_mode) or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                    raise RuntimeError("release code changed")
            elif row["type"] == "directory":
                if not stat.S_ISDIR(info.st_mode):
                    raise RuntimeError("release directory changed")
            elif row["type"] == "symlink":
                if not stat.S_ISLNK(info.st_mode) or os.readlink(path) != row["target"] or not path.resolve().is_relative_to(release):
                    raise RuntimeError("release link changed")
            else:
                raise RuntimeError("unsupported release object")
            seen.add(relative)
    if seen != set(rows):
        raise RuntimeError("release inventory changed")
    sys.path.insert(0, str(release))
    from ops.executive_os.release_manifest import verify
    verify(release, COMMIT, TREE)
    from integrations.session_bridge.bound_launch_capture.owner_assembly import run_private_owner_bridge
    return run_private_owner_bridge(**ARGUMENTS)

RELEASE = ''' + repr(str(release_root)) + '\nCOMMIT = ' + repr(commit_sha)
        + '\nTREE = ' + repr(tree_sha) + '\nMANIFEST = ' + repr(manifest_sha256)
        + '\nARGUMENTS = ' + repr(arguments) + '''
if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("Fixed attended bridge unavailable; no automatic retry", file=sys.stderr)
        raise SystemExit(2)
''').encode()


def build_finite_worker_artifacts(*, primary_config, worker_id, worker_user, worker_group,
        worker_uid, worker_gid, control_gid, runtime_root, definition_dir, socket_path,
        binary: BinaryAttestation, binary_receipt_path, binary_receipt_sha256,
        realm_generation, release_root, release_commit, release_tree, release_manifest_sha256, python_binary,
        host_ref, model_class, execution_profile_digest, service_source_sha256=None,
        permission_profile_sha256=None, routing_root_id, routing_parent_run_id,
        max_turns=2, capacity_capability_id=None, native_capacity_enrollment=None):
    """Return exact bytes for one owner-selected secondary worker, never publish.

    primary_config is the existing installed primary definition supplied by its
    owner, used only for collision refusal. Digests describe owner-reviewed
    artifacts; this renderer does not claim they have been installed or admitted.
    """
    for value in (worker_id, worker_user, worker_group, host_ref):
        _identifier(value)
    for value in (routing_root_id, routing_parent_run_id):
        if type(value) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value) is None:
            raise AttendedDefinitionError('original routing correlation required')
    if (type(primary_config) is not dict or not
            {'worker_id', 'worker_user', 'worker_uid', 'worker_gid', 'provider_home', 'control_uid'} <= set(primary_config)):
        raise AttendedDefinitionError('existing primary definition required')
    control_uid = primary_config['control_uid']
    for value in (worker_uid, worker_gid, control_uid, control_gid, realm_generation):
        if type(value) is not int or value <= 0:
            raise AttendedDefinitionError('positive exact principal/generation required')
    if (control_uid != bridge.CONTROL_UID or worker_uid in (control_uid, primary_config['worker_uid'])
            or worker_gid in (control_gid, primary_config['worker_gid'])
            or worker_id in ('codex-01', primary_config['worker_id'])
            or worker_user in ('_mastermind_worker', primary_config['worker_user'])):
        raise AttendedDefinitionError('secondary worker cannot reuse the primary or Control principal')
    if type(max_turns) is not int or not 1 <= max_turns <= MAX_TURNS_LIMIT:
        raise AttendedDefinitionError('finite turn ceiling required')
    runtime = _path(runtime_root)
    definitions = _path(definition_dir)
    release = _path(release_root)
    python = _path(python_binary)
    socket = _path(socket_path)
    receipt = _path(binary_receipt_path)
    primary_home = _path(primary_config['provider_home'])
    home = runtime/'workers'/worker_id/'provider-home'
    if home == primary_home or home.is_relative_to(primary_home) or primary_home.is_relative_to(home):
        raise AttendedDefinitionError('secondary HOME collides with primary')
    for path in (runtime, definitions, socket, receipt):
        if path == release or path.is_relative_to(release) or release.is_relative_to(path):
            raise AttendedDefinitionError('installation artifacts must not change the sealed release')
    _sha(release_commit, 40); _sha(release_tree, 40)
    _sha(release_manifest_sha256)
    if release.name != release_commit:
        raise AttendedDefinitionError('exact immutable release directory required')
    _sha(binary_receipt_sha256)
    _sha(execution_profile_digest)
    expected_permission = finite_read_permission_digest()
    if ((service_source_sha256 is not None and service_source_sha256 != release_manifest_sha256)
            or (permission_profile_sha256 is not None and permission_profile_sha256 != expected_permission)):
        raise AttendedDefinitionError('source/permission digest differs from canonical producer')
    service_source_sha256 = release_manifest_sha256
    permission_profile_sha256 = expected_permission
    _reviewed_binary(binary)
    if type(binary) is not BinaryAttestation or binary.uid != 0 or binary.path != binary.real_path:
        raise AttendedDefinitionError('actual canonical root binary observation required')
    _path(binary.path)
    if binary_receipt_sha256 != _digest(_json({'schema_version': 'mastermind.attended_claude_binary/v1',
                                              'binary': dataclasses.asdict(binary)})):
        raise AttendedDefinitionError('binary receipt must bind the exact observed executable')
    binding = get_binding(canary.BINDING)
    profile = get_profile(binding.profile_id)
    _reviewed_binding_and_profile(binding, profile)
    if binding.autonomous_allowed or profile.autonomous_allowed or binding.implementation_state == 'SPEC_ONLY':
        raise AttendedDefinitionError('finite reviewed binding required')
    model = _reviewed_model(binding, profile, model_class)
    label = 'com.mastermind.executive.fabric.' + worker_id
    socket_name = 'AttendedFabric'
    worker = dict(schema_version='mastermind.executive_worker_broker_config/v5',
        control_uid=control_uid, control_gid=control_gid, worker_uid=worker_uid, worker_gid=worker_gid,
        allowed_supplementary_gids=[], worker_user=worker_user, worker_id=worker_id,
        workspace_root=str(runtime/'workers'/worker_id/'jobs/workspaces'),
        run_root=str(runtime/'workers'/worker_id/'jobs/runs'),
        provider_home=str(home), claude_binary=binary.path,
        claude_attestation_receipt=str(receipt), claude_attestation_sha256=binary_receipt_sha256,
        allowed_claude_versions=[binary.version], launchd_socket_name=socket_name,
        uid_sweep_receipt=str(runtime/'workers'/worker_id/'state/uid-sweep.json'),
        require_secret_canary=True, operator_harness_armed=False, harness_binding_id=canary.BINDING,
        subscription_realm_enrollment={'generation': realm_generation, 'binding_id': canary.BINDING},
        attended_secret_canary=dict(canary.PRESET))
    if capacity_capability_id is not None:
        # Actual Provider Control identity, supplied by its existing owner.
        # Omission preserves older staging bytes but cannot register capacity.
        if (type(capacity_capability_id) is not str
                or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', capacity_capability_id) is None):
            raise AttendedDefinitionError('exact capacity capability identity required')
        worker['capacity_capability_id'] = capacity_capability_id
    if native_capacity_enrollment is not None:
        from ops.executive_os.capacity_source_contract import validate_native_subscription_capacity_enrollment
        if capacity_capability_id is None:
            raise AttendedDefinitionError('native enrollment requires its Provider Control identity')
        stanza = validate_native_subscription_capacity_enrollment(native_capacity_enrollment)
        if stanza['host_ref'] != host_ref:
            raise AttendedDefinitionError('native enrollment differs from physical host owner')
        worker['native_capacity_enrollment'] = stanza
    worker_bytes = _json(worker)
    physical = FabricHostBinding(socket_path=str(socket), host_ref=host_ref, worker_id=worker_id,
        worker_uid=worker_uid, worker_gid=worker_gid, bridge_uid=worker_uid,
        provider=binding.provider, model=model, provider_home=str(home),
        worker_source_config_digest=_digest(worker_bytes), execution_profile_digest=execution_profile_digest,
        service_source_sha256=service_source_sha256, binary_sha256=binary.sha256,
        permission_profile_sha256=permission_profile_sha256)
    bindings_bytes = _json({'schema_version': CONFIG_SCHEMA_VERSION, 'bindings': [dataclasses.asdict(physical)]})
    _bindings(bindings_bytes)  # actual closed-schema consumer
    bridge_doc = dict(schema_version=bridge.CONFIG_SCHEMA_VERSION, adapter_id=bridge.ADAPTER_ID,
        bridge_uid=worker_uid, control_uid=control_uid, launchd_socket_name=socket_name,
        socket_path=str(socket), workspace_root=worker['workspace_root'], run_root=worker['run_root'],
        max_request_bytes=65536, max_response_bytes=262144, request_timeout_seconds=30,
        validation_commands=[])
    bridge.BridgeConfig.from_document(bridge_doc)
    arguments = dict(config_path=str(definitions/'bridge.json'), bindings_path=str(definitions/'bindings.json'),
        bindings_sha256=_digest(bindings_bytes), realm_config_path=str(definitions/'worker.json'),
        host_ref=host_ref, worker_id=worker_id, routing_root_id=routing_root_id,
        routing_parent_run_id=routing_parent_run_id,
        active_dir=str(runtime/'workers'/worker_id/'active'), model_class=model_class, max_turns=max_turns,
        verified_release_manifest_sha256=release_manifest_sha256)
    plist = dict(Label=label, ProgramArguments=[str(python), '-I', '-S', '-B', str(definitions/'owner_entry.py')],
        WorkingDirectory=str(release), UserName=worker_user, GroupName=worker_group, InitGroups=False,
        EnvironmentVariables={'HOME': str(home), 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'},
        Sockets={socket_name: dict(SockFamily='Unix', SockType='stream', SockPassive=True,
            SockPathName=str(socket), SockPathOwner=0, SockPathGroup=control_gid, SockPathMode=0o660)},
        RunAtLoad=False, KeepAlive=False, Disabled=True, Umask=0o077)
    return {'worker.json': worker_bytes, 'bridge.json': _json(bridge_doc),
        'bindings.json': bindings_bytes, 'owner_entry.py': _entry(release, release_commit, release_tree,
            release_manifest_sha256, arguments),
        label + '.plist': plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=True)}
