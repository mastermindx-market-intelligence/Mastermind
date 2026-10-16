"""Complete the fixed initial finite enrollment before Control selects it.

The installed root publisher qualifies actual source, principal, private
credential custody and the complete original definition. A single Darwin
directory exchange publishes all five canonical files together. Its occupied
staging directory is retained after success or failure; this first-enrollment
path never retries, cleans up, rotates a credential, arms or starts a service.
"""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import copy
import ctypes
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys

from ops.executive_os import autonomy_control as owner
from ops.executive_os.attended_worker_definition import build_finite_worker_artifacts
from ops.executive_os.finite_reference_assignment import (
    prepare_finite_reference_stanza, require_initial_reference_context,
)
from ops.executive_os.finite_service_lifecycle import (
    DEFINITION, LABEL, PYTHON, ROOT_ID, SOCKET, SYSTEM, checked_command,
    parse_override, protected_bytes,
)

STAGING = DEFINITION.with_name(DEFINITION.name + '.initial-enrollment')
NAMES = frozenset({'worker.json', 'bridge.json', 'bindings.json',
                   'owner_entry.py', LABEL + '.plist'})
PRIMARY_SHA256 = 'c69f44c3c6e17f40d2deb674be5c9a999e0c5dee9d06e71309fb244c96ce0faf'


class EnrollmentCompletionError(RuntimeError):
    def __init__(self, *, effect_unknown=False):
        self.effect_unknown = effect_unknown
        super().__init__('FINITE_ENROLLMENT_EFFECT_UNKNOWN' if effect_unknown
                         else 'FINITE_ENROLLMENT_UNAVAILABLE')


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _absent(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise EnrollmentCompletionError()


def prepare_completion(original, rendering_inputs):
    """Pure exact preimage check and canonical bytes, never an enrollment grant."""
    if (type(original) is not dict or set(original) != NAMES
            or any(type(raw) is not bytes for raw in original.values())
            or type(rendering_inputs) is not dict):
        raise EnrollmentCompletionError()
    worker = json.loads(original['worker.json'])
    stanza = worker.get('native_capacity_enrollment')
    if (type(stanza) is not dict or stanza.get('enrollment_state') != 'unenrolled'
            or worker.get('subscription_realm_enrollment', {}).get('generation') != 1):
        raise EnrollmentCompletionError()
    retained = prepare_finite_reference_stanza(
        previous_worker=worker, realm_generation=1,
        registration_source=stanza['registration_source'], existing_host_ref=stanza['host_ref'])
    if retained != stanza or build_finite_worker_artifacts(**rendering_inputs) != original:
        raise EnrollmentCompletionError()
    proposed = copy.deepcopy(rendering_inputs)
    proposed['native_capacity_enrollment'] = dict(retained, enrollment_state='enrolled')
    target = build_finite_worker_artifacts(**proposed)
    if {name for name in NAMES if target[name] != original[name]} != {
            'worker.json', 'bindings.json', 'owner_entry.py'}:
        raise EnrollmentCompletionError()
    return target


def execute_completion(host):
    """One qualified publication; a staging/effect failure is sticky to its owner."""
    effect = False
    try:
        with host.interval():
            before, original, inputs = host.snapshot()
            target = prepare_completion(original, inputs)
            host.require_staging_absent()
            host.recheck(before, original)
            effect = True
            host.stage(target)
            host.recheck(before, original)
            host.verify_staged(target)
            host.exchange()
            host.verify_published(before, original, target)
            return {'state': 'ENROLLED', 'artifact_sha256': {
                name: _digest(raw) for name, raw in target.items()},
                'provider_auth': 'UNKNOWN', 'provider_health': 'UNKNOWN',
                'provider_quota': 'UNKNOWN', 'service_started': False,
                'control_selected': False, 'runtime_admission': False}
    except Exception:
        raise EnrollmentCompletionError(effect_unknown=effect) from None


class ProductionCompletionHost:
    """Only the fixed, installed root owner can exercise the modifying path.

    Invoke through the existing pinned root bootstrap after release verification.
    Expected hashes are the retained original initial-publication result, never
    hashes collected by this invocation to adopt an unknown prior effect.
    """
    def __init__(self, *, expected_sha, manifest_sha256, original_artifact_sha256):
        self.sha = expected_sha
        self.manifest = manifest_sha256
        self.original_hashes = copy.deepcopy(original_artifact_sha256)
        self.owner = owner.ProductionCeoSubmitHost()
        self.fd = None

    @contextmanager
    def interval(self):
        if (os.geteuid() != 0 or sys.platform != 'darwin' or not sys.flags.isolated
                or not sys.dont_write_bytecode
                or type(self.sha) is not str or re.fullmatch('[0-9a-f]{40}', self.sha) is None
                or type(self.manifest) is not str or re.fullmatch('[0-9a-f]{64}', self.manifest) is None
                or type(self.original_hashes) is not dict or set(self.original_hashes) != NAMES
                or any(type(v) is not str or re.fullmatch('[0-9a-f]{64}', v) is None
                       for v in self.original_hashes.values())
                or Path(__file__).absolute() != SYSTEM/'releases'/self.sha/'ops/executive_os/finite_enrollment_completion.py'):
            raise EnrollmentCompletionError()
        self.owner._config_root_safe()
        fd = os.open(owner.CONFIG_ROOT, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
            if _identity(os.fstat(fd)) != _identity(owner.CONFIG_ROOT.lstat()):
                raise EnrollmentCompletionError()
            self.fd = fd
            self.owner._config_root_safe()
            self.require_staging_absent()
            # Resolve the actual SDK-supported syscall before any publication.
            self._libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
            self._swap = self._libc.renameatx_np
            self._swap.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                                   ctypes.c_char_p, ctypes.c_uint]
            self._swap.restype = ctypes.c_int
            yield
        finally:
            self.fd = None
            os.close(fd)

    def require_staging_absent(self):
        _absent(STAGING)

    def _require_same_config_root(self):
        self.owner._config_root_safe()
        if self.fd is None:
            raise EnrollmentCompletionError()
        held, visible = os.fstat(self.fd), owner.CONFIG_ROOT.lstat()
        if (held.st_dev, held.st_ino) != (visible.st_dev, visible.st_ino):
            raise EnrollmentCompletionError()

    @staticmethod
    def _read_artifacts(directory):
        from control_plane.fs_security import has_macos_acl
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (0, 0, 0o755)
                or has_macos_acl(directory, expected_identity=info)
                or set(p.name for p in directory.iterdir()) != NAMES):
            raise EnrollmentCompletionError()
        return {name: protected_bytes(directory/name) for name in NAMES}

    def snapshot(self):
        # Keep the incumbent no-follow/ancestor/ACL observations alive through
        # the complete snapshot; their exit checks also detect named replacement.
        with ExitStack() as custody:
            return self._snapshot(custody)

    def _snapshot(self, custody):
        from control_plane.codex_provider_realm import _native_open, _native_read_config
        from control_plane.codex_worker import _assert_binary_unchanged
        from control_plane.executive_fabric_composition import _bindings
        from control_plane.executive_physical_resources import load_physical_resource_policy
        from control_plane.model_router import ModelRouter
        from control_plane.worker_execution_contract import BinaryAttestation
        from ops.executive_os.capacity_source_contract import validate_native_registration_document
        from ops.executive_os.credential_rotation_interlock import assert_credential_mutation_disarmed
        from ops.executive_os.subscription_provider_credential import (
            _assert_worker_quiescent, _credential_metadata, verify_provider_credential,
        )
        self._require_same_config_root()
        if self.owner.require_exact_install(self.sha) != self.sha:
            raise EnrollmentCompletionError()
        self.owner.require_transaction_absent()
        assert_credential_mutation_disarmed()
        prior = self.owner.load_unarmed_configs(self.sha)
        require_initial_reference_context(dict(prior.control), dict(prior.worker), load_physical_resource_policy())
        if (prior.worker_sha256 != PRIMARY_SHA256
                or any(prior.control.get(k) is not False for k in (
                    'coo_autonomy_armed', 'coo_operator_harness_armed',
                    'coo_foreground_only', 'ceo_submit_armed', 'fabric_bridge_armed'))
                or self.owner._loaded_observe_only(LABEL)
                or parse_override(checked_command(['/bin/launchctl', 'print-disabled', 'system']).stdout.decode()) not in {'default', 'disabled'}):
            raise EnrollmentCompletionError()
        _absent(Path(SOCKET))
        artifacts = self._read_artifacts(DEFINITION)
        worker = json.loads(artifacts['worker.json'])
        stanza = worker['native_capacity_enrollment']
        retained = prepare_finite_reference_stanza(previous_worker=worker, realm_generation=1,
            registration_source=stanza['registration_source'], existing_host_ref=stanza['host_ref'])
        if worker['subscription_realm_enrollment']['generation'] != 1:
            raise EnrollmentCompletionError()
        user = pwd.getpwnam(worker['worker_user']); group = grp.getgrnam(worker['worker_user'])
        uid, gid = worker['worker_uid'], worker['worker_gid']
        if (user.pw_uid, user.pw_gid, group.gr_gid, user.pw_dir, user.pw_shell) != (
                uid, gid, gid, worker['provider_home'], '/usr/bin/false'):
            raise EnrollmentCompletionError()
        _assert_worker_quiescent(uid)
        _, home_info = custody.enter_context(_native_open(
            Path(worker['provider_home']), directory=True, private_uid=uid))
        if (home_info.st_uid, home_info.st_gid, stat.S_IMODE(home_info.st_mode)) != (uid, gid, 0o700):
            raise EnrollmentCompletionError()
        credential = verify_provider_credential(worker)
        metadata = _credential_metadata(credential, worker_uid=uid, worker_gid=gid)
        release = SYSTEM/'releases'/self.sha
        manifest_raw = protected_bytes(release/'.executive-release-manifest.json')
        if _digest(manifest_raw) != self.manifest:
            raise EnrollmentCompletionError()
        manifest = json.loads(manifest_raw)
        receipt_path = SYSTEM/'config/claude-minimax-finite-01-attestation.json'
        if Path(worker['claude_attestation_receipt']) != receipt_path:
            raise EnrollmentCompletionError()
        receipt_raw = protected_bytes(receipt_path, mode=0o440, gid=gid)
        receipt = json.loads(receipt_raw)
        if (_digest(receipt_raw) != worker['claude_attestation_sha256']
                or set(receipt) != {'schema_version', 'binary'}
                or receipt['schema_version'] != 'mastermind.attended_claude_binary/v1'):
            raise EnrollmentCompletionError()
        binary = BinaryAttestation(**receipt['binary'])
        custody.enter_context(_native_open(Path(binary.path)))
        _assert_binary_unchanged(binary)
        physical, = _bindings(artifacts['bindings.json'])
        if physical.host_ref != retained['host_ref']:
            raise EnrollmentCompletionError()
        profile = ModelRouter.load().capability_registry.resolve('fabric.attended.claude.bounded.v1')
        inputs = dict(primary_config=dict(prior.worker), worker_id=worker['worker_id'],
            worker_user=user.pw_name, worker_group=group.gr_name, worker_uid=uid, worker_gid=gid,
            control_gid=worker['control_gid'], runtime_root='/private/var/db/mastermind-executive',
            definition_dir=str(DEFINITION), socket_path=SOCKET, binary=binary,
            binary_receipt_path=str(receipt_path), binary_receipt_sha256=_digest(receipt_raw),
            realm_generation=1, release_root=str(release), release_commit=self.sha,
            release_tree=manifest['tree_sha'], release_manifest_sha256=self.manifest,
            python_binary=PYTHON, host_ref=retained['host_ref'], model_class='routine',
            execution_profile_digest=profile.profile_digest, routing_root_id=ROOT_ID,
            routing_parent_run_id=ROOT_ID, max_turns=2,
            capacity_capability_id=worker['capacity_capability_id'], native_capacity_enrollment=stanza)
        if build_finite_worker_artifacts(**inputs) != artifacts:
            raise EnrollmentCompletionError()
        source = stanza['registration_source']
        export_path = SYSTEM/'config/capacity-source-components-native-v2'/(source['release_commit']+'.json')
        export = _native_read_config(export_path, source['export_sha256'])
        row = validate_native_registration_document(worker, export)
        if (row['provider'], row['credential_kind']) != ('minimax', 'api_key'):
            raise EnrollmentCompletionError()
        if (_native_read_config(export_path, source['export_sha256']) != export
                or _identity(_credential_metadata(credential, worker_uid=uid, worker_gid=gid)) != _identity(metadata)
                or self.owner._configs()[2:4] != (prior.control_sha256, prior.worker_sha256)):
            raise EnrollmentCompletionError()
        return {'credential': _identity(metadata), 'configs': (prior.control_sha256, prior.worker_sha256),
                'definition': _identity(DEFINITION.lstat()),
                'export': _digest(json.dumps(export, sort_keys=True).encode())}, artifacts, inputs

    def recheck(self, before, original):
        current, actual, _ = self.snapshot()
        if (current != before or actual != original
                or {name: _digest(raw) for name, raw in actual.items()} != self.original_hashes):
            raise EnrollmentCompletionError()
        self._original_identity = current['definition']

    def stage(self, target):
        self.require_staging_absent()
        os.mkdir(STAGING, 0o700)  # Exclusive, retained on every later failure.
        os.chown(STAGING, 0, 0)
        for name in sorted(NAMES):
            owner._atomic_file(STAGING/name, target[name], mode=0o444, uid=0, gid=0, replace=False)
        os.chmod(STAGING, 0o755, follow_symlinks=False)
        owner._fsync_directory(STAGING)
        owner._fsync_directory(owner.CONFIG_ROOT)
        self.verify_staged(target)

    def verify_staged(self, target):
        if self._read_artifacts(STAGING) != target:
            raise EnrollmentCompletionError()
        self._staged_identity = _identity(STAGING.lstat())

    def exchange(self):
        self._require_same_config_root()
        if (_identity(DEFINITION.lstat()) != self._original_identity
                or _identity(STAGING.lstat()) != self._staged_identity):
            raise EnrollmentCompletionError()
        # Darwin SDK sys/stdio.h: RENAME_SWAP=0x2. Both directory names are
        # fixed children of the held incumbent configuration-directory mutex.
        ctypes.set_errno(0)
        if self._swap(self.fd, os.fsencode(STAGING.name), self.fd, os.fsencode(DEFINITION.name), 0x2) != 0:
            raise EnrollmentCompletionError(effect_unknown=True)
        os.fsync(self.fd)

    def verify_published(self, before, original, target):
        current, actual, _ = self.snapshot()
        # A successful exchange changes directory ctime, but must retain each
        # exact held directory inode; all credential/config/source facts agree.
        prior_definition = before['definition']
        before = dict(before); current = dict(current)
        del before['definition']; selected = current.pop('definition')
        archived = _identity(STAGING.lstat())
        if (current != before or actual != target or self._read_artifacts(STAGING) != original
                or selected[:2] != self._staged_identity[:2]
                or archived[:2] != prior_definition[:2]):
            raise EnrollmentCompletionError(effect_unknown=True)
