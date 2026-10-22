#!/usr/bin/env python3
"""Fixed finite bridge lifecycle behind the installed service controller.

This owner does not arm Control, enroll a credential, admit an account or start
a provider task. A failed modifying call leaves its original effect unknown.
Only the read-only status path may subsequently observe it; start and stop
refuse partial states rather than repeating an earlier modifying call.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import stat
import subprocess
import sys
import time

LABEL = 'com.mastermind.executive.fabric.minimax-finite-01'
SYSTEM = Path('/Library/Application Support/MastermindExecutive')
DEFINITION = SYSTEM / 'config/fabric-minimax-finite-01'
PLIST = DEFINITION / (LABEL + '.plist')
SOCKET = '/var/run/mastermind-executive/fabric-minimax-finite-01.sock'
PYTHON = '/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12'
ROOT_ID = '01a11e90-4b5d-7f53-b966-8aaaad38701f'
ACTIONS = frozenset({'start-finite', 'stop-finite', 'status-finite'})


class LifecycleError(RuntimeError):
    def __init__(self, code, *, effect_unknown=False):
        self.code = code
        self.effect_unknown = effect_unknown
        super().__init__(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def run_lifecycle(host, action, expected_sha):
    """Small state machine; tests substitute the host, never production verdicts."""
    if action not in ACTIONS or type(expected_sha) is not str or re.fullmatch(r'[0-9a-f]{40}', expected_sha) is None:
        raise LifecycleError('arguments_invalid')
    effect = False
    stage = 'preflight'
    try:
        with host.qualified_interval(expected_sha) as snapshot:
            initial = host.registration()
            override = host.override()
            if action == 'status-finite':
                if initial['state'] == 'absent':
                    host.require_idle(snapshot, None)
                    host.recheck(snapshot)
                    if host.registration() != initial or host.override() != override:
                        raise LifecycleError('status_changed')
                    return dict(state='ABSENT', enabled_override=override,
                                release=expected_sha, effect=False)
                ready = host.readiness(snapshot, initial)
                host.recheck(snapshot)
                if host.registration() != initial or host.override() != override:
                    raise LifecycleError('status_changed')
                return dict(state='READY', release=expected_sha, readiness=ready,
                            enabled_override=override, effect=False)

            if action == 'start-finite':
                # enabled+absent can be a crashed earlier enable. Never adopt it.
                if initial['state'] != 'absent' or override not in {'disabled', 'default'}:
                    raise LifecycleError('start_requires_unloaded_unenabled')
                host.require_idle(snapshot, None)
                host.recheck(snapshot)
                if host.registration() != initial or host.override() != override:
                    raise LifecycleError('preimage_changed')
                stage = 'enable'
                effect = True
                host.modify('enable')
                if host.override() != 'enabled' or host.registration()['state'] != 'absent':
                    raise LifecycleError('enable_unconfirmed')
                stage = 'bootstrap'
                host.modify('bootstrap')
                loaded = host.registration()
                if loaded['state'] not in {'registered', 'running'}:
                    raise LifecycleError('bootstrap_unconfirmed')
                if loaded['state'] != 'running':
                    stage = 'kickstart'
                    host.modify('kickstart')
                stage = 'readiness'
                for attempt in range(31):
                    current = host.registration()
                    if current['state'] == 'running':
                        ready = host.readiness(snapshot, current)
                        host.recheck(snapshot)
                        if host.registration() != current or host.override() != 'enabled':
                            raise LifecycleError('ready_generation_changed')
                        return dict(state='READY', release=expected_sha,
                                    readiness=ready, effect=True)
                    if current['state'] != 'registered':
                        raise LifecycleError('startup_registration_lost')
                    if attempt < 30:
                        host.pause()
                raise LifecycleError('readiness_deadline')

            if initial['state'] != 'running' or override != 'enabled':
                raise LifecycleError('stop_requires_enabled_running_original')
            before = host.readiness(snapshot, initial)
            host.require_idle(snapshot, initial['pid'])
            host.recheck(snapshot)
            if (host.registration() != initial or host.override() != override
                    or host.readiness(snapshot, initial) != before):
                raise LifecycleError('stop_generation_changed')
            stage = 'disable'
            effect = True
            host.modify('disable')
            if host.override() != 'disabled' or host.registration() != initial:
                raise LifecycleError('disable_unconfirmed')
            stage = 'bootout'
            host.modify('bootout')
            stage = 'absence'
            for attempt in range(31):
                current = host.registration()
                if current['state'] == 'absent':
                    host.require_idle(snapshot, None)
                    host.recheck(snapshot)
                    if host.registration() != current or host.override() != 'disabled':
                        raise LifecycleError('absence_changed')
                    return dict(state='ABSENT', release=expected_sha,
                                prior_readiness=before, effect=True)
                if current != initial:
                    raise LifecycleError('stop_generation_changed')
                if attempt < 30:
                    host.pause()
            raise LifecycleError('absence_deadline')
    except Exception as exc:
        code = exc.code if isinstance(exc, LifecycleError) else 'qualification_unavailable'
        raise LifecycleError(stage + ':' + code, effect_unknown=effect) from None


def parse_registration(raw, *, gateway=False):
    """Require one top-level fixed launchd job and unambiguous PID/state/path."""
    if type(raw) is not str or len(raw.encode()) > 262144 or '\x00' in raw:
        raise LifecycleError('launchd_output_invalid')
    label = 'com.mastermind.executive.mcp' if gateway else LABEL
    path = '/Library/LaunchDaemons/' + label + '.plist' if gateway else str(PLIST)
    lines = raw.splitlines()
    if not lines or not re.fullmatch(r'system/' + re.escape(label) + r' = \{', lines[0]):
        raise LifecycleError('launchd_label_mismatch')
    fields = {}
    depth = 0
    for line in lines:
        if depth == 1 and line.startswith('\t') and not line.startswith('\t\t'):
            match = re.fullmatch(r'\t(state|pid|path) = (.+)', line)
            if match:
                key, value = match.groups()
                if key in fields:
                    raise LifecycleError('launchd_duplicate_field')
                fields[key] = value
        depth += line.count('{') - line.count('}')
        if depth < 0:
            raise LifecycleError('launchd_structure_invalid')
    if depth != 0 or fields.get('path') != path:
        raise LifecycleError('launchd_path_mismatch')
    state = fields.get('state')
    pid = fields.get('pid')
    if state == 'running' and pid and re.fullmatch(r'[1-9][0-9]{0,9}', pid):
        return dict(state='running', pid=int(pid))
    if state in {'waiting', 'not running', 'spawn scheduled'} and pid is None:
        return dict(state='registered', pid=None)
    raise LifecycleError('launchd_state_unqualified')


def parse_override(raw):
    if type(raw) is not str or len(raw.encode()) > 262144 or '\x00' in raw:
        raise LifecycleError('launchd_override_invalid')
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) < 2 or lines[0] != 'disabled services = {' or lines[-1] != '}':
        raise LifecycleError('launchd_override_invalid')
    rows = {}
    for line in lines[1:-1]:
        match = re.fullmatch(r'"([A-Za-z0-9._-]+)" => (enabled|disabled|true|false)', line)
        if not match or match[1] in rows:
            raise LifecycleError('launchd_override_invalid')
        rows[match[1]] = match[2]
    value = rows.get(LABEL)
    return 'default' if value is None else 'disabled' if value in {'disabled', 'true'} else 'enabled'


def checked_command(argv, *, allowed=(0,)):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=15, check=False,
                            env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'})
    if result.returncode not in allowed or len(result.stdout) > 262144 or len(result.stderr) > 262144:
        raise LifecycleError('native_command_failed')
    return result


def protected(path, directory=False):
    for item in (path, *path.parents):
        info = item.lstat()
        is_dir = directory or item != path
        if (info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISDIR(info.st_mode) if is_dir else stat.S_ISREG(info.st_mode))):
            raise RuntimeError("untrusted installation source")

def verify_release_before_import(commit, manifest_digest):
    release_root = SYSTEM / "releases" / commit
    if Path(__file__).absolute() != release_root / "ops/executive_os/finite_service_lifecycle.py":
        raise RuntimeError("fixed installed lifecycle entry required")
    protected(Path(__file__).absolute())
    release = release_root
    protected(release, directory=True)
    manifest = release / ".executive-release-manifest.json"
    protected(manifest)
    manifest_bytes = manifest.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_digest:
        raise RuntimeError("release manifest changed")
    document = json.loads(manifest_bytes)
    if document.get("commit_sha") != commit or re.fullmatch(r"[0-9a-f]{40}", str(document.get("tree_sha"))) is None:
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
    verify(release, commit, document["tree_sha"])
    return document


def protected_bytes(path, *, mode=0o444, gid=0):
    from ops.executive_os import autonomy_control as owner
    from control_plane.fs_security import has_macos_acl
    for parent in path.parents:
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022 or has_macos_acl(parent, expected_identity=info)):
            raise LifecycleError('untrusted_definition_ancestor')
    raw, _ = owner._read_root_file(path, modes=frozenset({mode}), uid=0, gid=gid)
    return raw


def bridge_readiness(config):
    """Live self facts only, called after the existing Control peer check."""
    import dataclasses
    from control_plane.executive_process_identity import _observe_process_instance
    from control_plane.executive_fabric_bridge_broker import load_config
    release = Path(__file__).absolute().parents[2]
    if (sys.platform != 'darwin' or re.fullmatch(r'[0-9a-f]{40}', release.name) is None
            or release != SYSTEM/'releases'/release.name
            or config.bridge_uid != 470 or config.control_uid != 450
            or str(config.socket_path) != SOCKET or sys.argv != [str(DEFINITION/'owner_entry.py')]
            or Path(sys.executable).resolve() != Path(PYTHON).resolve()
            or (os.getuid(), os.geteuid(), os.getgid(), os.getegid()) != (470, 470, 470, 470)):
        raise LifecycleError('finite_service_identity_invalid')
    before = _observe_process_instance(os.getpid())
    if load_config(DEFINITION/'bridge.json') != config:
        raise LifecycleError('bridge_configuration_changed')
    manifest = protected_bytes(release/'.executive-release-manifest.json')
    doc = json.loads(manifest)
    if doc['commit_sha'] != release.name:
        raise LifecycleError('bridge_release_changed')
    hashes = {name: digest(protected_bytes(DEFINITION/name)) for name in
              ('worker.json', 'bridge.json', 'bindings.json', 'owner_entry.py', LABEL+'.plist')}
    groups = sorted(set(os.getgroups()))
    if set(groups) - {470} or _observe_process_instance(os.getpid()) != before:
        raise LifecycleError('bridge_groups_or_generation_invalid')
    return dict(schema_version='mastermind.finite_service_readiness/v1',
                pid=os.getpid(), real_uid=os.getuid(), effective_uid=os.geteuid(),
                real_gid=os.getgid(), effective_gid=os.getegid(), supplementary_gids=groups,
                process_instance=dataclasses.asdict(before), release_sha=release.name,
                manifest_sha256=digest(manifest), artifact_sha256=hashes)


class ProductionHost:
    def __init__(self, manifest_digest):
        self.manifest_digest = manifest_digest
        self.sha = None
        self.owner = None

    def qualify(self):
        import dataclasses
        import grp
        import pwd
        from ops.executive_os import autonomy_control as owner
        from ops.executive_os.attended_worker_definition import build_finite_worker_artifacts
        from ops.executive_os.credential_rotation_interlock import assert_credential_mutation_disarmed
        from control_plane.executive_fabric_composition import _bindings
        from control_plane.worker_execution_contract import BinaryAttestation
        from control_plane.codex_worker import _assert_binary_unchanged
        from control_plane.model_router import ModelRouter
        from control_plane.fs_security import has_macos_acl
        if self.owner.require_exact_install(self.sha) != self.sha:
            raise LifecycleError('installed_release_changed')
        self.owner.require_transaction_absent()
        self.owner.require_services_already_stopped()
        self.owner.require_service_uids_quiescent()
        assert_credential_mutation_disarmed()
        prior = self.owner.load_unarmed_configs(self.sha)
        # The existing credential interlock has a narrower historical scope.
        # Every current Control frontier and the primary worker must be an
        # explicit boolean false before this separate finite lifecycle effect.
        if (any(prior.control.get(key) is not False for key in (
                'coo_autonomy_armed', 'coo_operator_harness_armed',
                'coo_foreground_only', 'ceo_submit_armed', 'fabric_bridge_armed'))
                or prior.worker.get('operator_harness_armed') is not False):
            raise LifecycleError('configs_not_wholly_disarmed')
        self.owner.require_runtime_quiescent(prior)
        if prior.worker_sha256 != 'c69f44c3c6e17f40d2deb674be5c9a999e0c5dee9d06e71309fb244c96ce0faf':
            raise LifecycleError('primary_worker_changed')
        self.owner._loaded_observe_only('com.mastermind.executive.backup') and self._refuse('backup_loaded')
        from ops.executive_os.gateway_refresh_preflight import qualify_gateway_refresh
        gateway_source = qualify_gateway_refresh(self.sha)
        gateway = parse_registration(checked_command(
            ['/bin/launchctl', 'print', 'system/com.mastermind.executive.mcp']).stdout.decode('utf-8', 'strict'), gateway=True)
        if gateway['state'] != 'running':
            raise LifecycleError('gateway_unavailable')
        user = pwd.getpwnam('_mastermind_minimax')
        group = grp.getgrnam('_mastermind_minimax')
        runtime = Path('/private/var/db/mastermind-executive')
        home = runtime/'workers/minimax-finite-01/provider-home'
        if (user.pw_uid, user.pw_gid, group.gr_gid, user.pw_dir, user.pw_shell) != (470, 470, 470, str(home), '/usr/bin/false'):
            raise LifecycleError('finite_principal_changed')
        if set(os.getgrouplist(user.pw_name, 470)) - {470, 12, 61, 100, 396}:
            raise LifecycleError('finite_directory_groups_changed')
        names = ('worker.json', 'bridge.json', 'bindings.json', 'owner_entry.py', LABEL+'.plist')
        if set(x.name for x in DEFINITION.iterdir()) != set(names):
            raise LifecycleError('definition_inventory_changed')
        artifacts = {name: protected_bytes(DEFINITION/name) for name in names}
        physical, = _bindings(artifacts['bindings.json'])
        worker = json.loads(artifacts['worker.json'])
        release = SYSTEM/'releases'/self.sha
        manifest = protected_bytes(release/'.executive-release-manifest.json')
        if digest(manifest) != self.manifest_digest:
            raise LifecycleError('manifest_changed')
        document = json.loads(manifest)
        receipt_path = Path(worker['claude_attestation_receipt'])
        if receipt_path != SYSTEM/'config/claude-minimax-finite-01-attestation.json':
            raise LifecycleError('binary_receipt_path_changed')
        receipt_raw = protected_bytes(receipt_path, mode=0o440, gid=470)
        if digest(receipt_raw) != worker['claude_attestation_sha256']:
            raise LifecycleError('binary_receipt_changed')
        receipt = json.loads(receipt_raw)
        if set(receipt) != {'schema_version', 'binary'} or receipt['schema_version'] != 'mastermind.attended_claude_binary/v1':
            raise LifecycleError('binary_receipt_invalid')
        binary = BinaryAttestation(**receipt['binary'])
        _assert_binary_unchanged(binary)
        profile = ModelRouter.load().capability_registry.resolve('fabric.attended.claude.bounded.v1')
        expected = build_finite_worker_artifacts(primary_config=dict(prior.worker),
            worker_id='minimax-finite-01', worker_user='_mastermind_minimax', worker_group='_mastermind_minimax',
            worker_uid=470, worker_gid=470, control_gid=450, runtime_root=str(runtime),
            definition_dir=str(DEFINITION), socket_path=SOCKET, binary=binary,
            binary_receipt_path=str(receipt_path), binary_receipt_sha256=digest(receipt_raw),
            realm_generation=1, release_root=str(release), release_commit=self.sha,
            release_tree=document['tree_sha'], release_manifest_sha256=self.manifest_digest,
            python_binary=PYTHON, host_ref=physical.host_ref, model_class='routine',
            execution_profile_digest=profile.profile_digest, routing_root_id=ROOT_ID,
            routing_parent_run_id=ROOT_ID, max_turns=2, capacity_capability_id=worker['capacity_capability_id'],
            native_capacity_enrollment=worker.get('native_capacity_enrollment'))
        if artifacts != expected:
            raise LifecycleError('canonical_definition_changed')
        from ops.executive_os.attended_worker_definition import build_finite_control_delta
        delta = build_finite_control_delta(definition_dir=str(DEFINITION), worker_artifacts=artifacts)
        if any(prior.control.get(key) != value for key, value in delta.items()):
            raise LifecycleError('finite_control_not_staged')
        active = runtime/'workers/minimax-finite-01/active'
        info = active.lstat()
        if (not stat.S_ISDIR(info.st_mode) or (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (470, 470, 0o700)
                or has_macos_acl(active, expected_identity=info)):
            raise LifecycleError('finite_activity_directory_untrusted')
        return dict(release_sha=self.sha, manifest_sha256=self.manifest_digest,
                    artifact_sha256={name: digest(raw) for name, raw in artifacts.items()},
                    control_sha256=prior.control_sha256, worker_sha256=prior.worker_sha256,
                    active_dir=str(active), python_image=str(Path(PYTHON).resolve(strict=True)),
                    gateway=gateway, gateway_source=gateway_source)

    @staticmethod
    def _refuse(code):
        raise LifecycleError(code)

    @contextmanager
    def qualified_interval(self, expected_sha):
        from ops.executive_os import autonomy_control as owner
        if os.geteuid() != 0 or sys.platform != 'darwin':
            raise LifecycleError('root_darwin_required')
        self.sha = expected_sha
        self.owner = owner.ProductionCeoSubmitHost()
        # Reuse the existing config-directory publication lock. No new lease,
        # registry, marker, cancellation or lifecycle authority is introduced.
        self.owner.require_transaction_absent()
        import fcntl
        self.owner._config_root_safe()
        fd = os.open(owner.CONFIG_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            # Same incumbent directory mutex, acquired without waiting on a
            # concurrent owner. An unknown/busy interval cannot become a retry.
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held, visible = os.fstat(fd), owner.CONFIG_ROOT.lstat()
            if (held.st_dev, held.st_ino) != (visible.st_dev, visible.st_ino):
                raise LifecycleError('config_lock_identity_changed')
            self.owner._config_root_safe()
            self.owner.require_transaction_absent()
            yield self.qualify()
        finally:
            os.close(fd)

    def recheck(self, snapshot):
        if self.qualify() != snapshot:
            raise LifecycleError('protected_generation_changed')

    def registration(self):
        result = checked_command(['/bin/launchctl', 'print', 'system/'+LABEL], allowed=(0, 113))
        if result.returncode == 113:
            return dict(state='absent', pid=None)
        return parse_registration(result.stdout.decode('utf-8', 'strict'))

    def override(self):
        return parse_override(checked_command(['/bin/launchctl', 'print-disabled', 'system']).stdout.decode('utf-8', 'strict'))

    def modify(self, verb):
        if verb not in {'enable', 'disable', 'bootstrap', 'kickstart', 'bootout'}:
            raise LifecycleError('unknown_fixed_verb')
        argv = ['/bin/launchctl', verb, 'system', str(PLIST)] if verb == 'bootstrap' else ['/bin/launchctl', verb, 'system/'+LABEL]
        checked_command(argv)

    def require_idle(self, snapshot, bridge_pid):
        from control_plane.executive_worker_broker import _ps_pids_for_uid
        prior = self.owner.load_unarmed_configs(self.sha)
        self.owner.require_runtime_quiescent(prior)
        expected = set() if bridge_pid is None else {bridge_pid}
        if set(_ps_pids_for_uid(470)) != expected or any(Path(snapshot['active_dir']).iterdir()):
            raise LifecycleError('finite_process_or_assignment_not_idle')
        if bridge_pid is None and Path(SOCKET).exists():
            raise LifecycleError('unowned_socket_remains')

    def readiness(self, snapshot, registration):
        from control_plane.darwin_process_image import inspect_owned_darwin_image
        if registration['state'] != 'running':
            raise LifecycleError('registered_not_ready')
        pid = registration['pid']
        before = inspect_owned_darwin_image(pid)
        result = checked_command(['/usr/bin/sudo', '-u', '_mastermind_exec', '/usr/bin/env', '-i',
            'HOME=/private/var/db/mastermind-executive/control/home', 'PATH=/usr/bin:/bin:/usr/sbin:/sbin',
            'LANG=C', 'LC_ALL=C', PYTHON, '-I', '-S', '-B', str(Path(__file__).absolute()),
            '--probe', '--expected-sha', self.sha, '--expected-manifest-sha256', self.manifest_digest])
        reply = json.loads(result.stdout)
        after = inspect_owned_darwin_image(pid)
        expected_keys = {'schema_version', 'pid', 'real_uid', 'effective_uid', 'real_gid', 'effective_gid',
                         'supplementary_gids', 'process_instance', 'release_sha', 'manifest_sha256', 'artifact_sha256', 'kernel_peer'}
        if (set(reply) != expected_keys or reply['schema_version'] != 'mastermind.finite_service_readiness/v1'
                or before != after or reply['pid'] != pid or reply['process_instance'] != before['exec_instance']
                or set(reply['kernel_peer']) != {'euid', 'pid', 'pidversion', 'audit_identity_digest'}
                or reply['kernel_peer']['euid'] != 470 or reply['kernel_peer']['pid'] != pid
                or reply['kernel_peer']['pidversion'] != before['exec_instance']['pidversion']
                or re.fullmatch(r'[0-9a-f]{64}', reply['kernel_peer']['audit_identity_digest']) is None
                or before['executable_path'] != snapshot['python_image']
                or any(reply[key] != 470 or before[key] != 470 for key in ('real_uid', 'effective_uid', 'real_gid', 'effective_gid'))
                or reply['supplementary_gids'] not in ([], [470])
                or any(reply[key] != snapshot[key] for key in ('release_sha', 'manifest_sha256', 'artifact_sha256'))):
            raise LifecycleError('same_generation_readiness_mismatch')
        return dict(reply, image_sha256=before['sha256'], boot_id=before['boot_id'])

    @staticmethod
    def pause():
        time.sleep(1)


def bind_live_peer(connection, reply):
    """Bind this response to the actual connected Darwin process, not getpeereid."""
    from control_plane.executive_peer_identity import capture_peer_identity, _current_capture
    peer = capture_peer_identity(connection)
    instance = reply.get('process_instance')
    if (type(instance) is not dict or type(reply.get('pid')) is not int
            or type(instance.get('pidversion')) is not int
            or peer.euid != 470 or peer.pid != reply['pid']
            or peer.pidversion != instance['pidversion']):
        raise LifecycleError('connected_process_mismatch')
    _current_capture(peer)
    return peer


def _socket_require(condition, code):
    if not condition:
        raise LifecycleError(code)


def socket_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def socket_acl_absent(path, before):
    """Observe this socket's own ACL without opening or connecting to it.

    Only native NULL+ENOENT with an unchanged full socket identity proves no
    allocated extended ACL. Any allocated ACL or other API result fails closed.
    """
    _socket_require(sys.platform == 'darwin' and stat.S_ISSOCK(before.st_mode), 'socket_acl_platform_or_type')
    _socket_require(socket_identity(path.lstat()) == socket_identity(before), 'socket_acl_identity_changed')
    lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    get_acl, free_acl = lib.acl_get_link_np, lib.acl_free
    get_acl.argtypes = [ctypes.c_char_p, ctypes.c_int]
    get_acl.restype = ctypes.c_void_p
    free_acl.argtypes = [ctypes.c_void_p]
    free_acl.restype = ctypes.c_int
    ctypes.set_errno(0)
    acl = get_acl(os.fsencode(path), 0x100)
    observed_errno = ctypes.get_errno()
    if acl:
        _socket_require(free_acl(acl) == 0, 'socket_acl_free_failed')
        raise LifecycleError('socket_allocated_acl')
    _socket_require(observed_errno == errno.ENOENT, 'socket_acl_observation_unknown')
    _socket_require(socket_identity(path.lstat()) == socket_identity(before), 'socket_acl_identity_changed')


def probe_socket():
    """One authenticated Control read, with no Runtime or backend operation."""
    import socket
    from control_plane.executive_worker_broker import (
        BROKER_REQUEST_SCHEMA_VERSION, BROKER_RESPONSE_SCHEMA_VERSION)
    from control_plane.executive_peer_identity import _current_capture
    from control_plane.executive_fabric_bridge_broker import _strict_json
    if (os.getuid(), os.geteuid(), os.getgid(), os.getegid()) != (450, 450, 450, 450):
        raise LifecycleError('control_probe_principal_invalid')
    path = Path(SOCKET)
    before = path.lstat()
    if (not stat.S_ISSOCK(before.st_mode) or
            (before.st_uid, before.st_gid, stat.S_IMODE(before.st_mode), before.st_nlink) != (0, 450, 0o660, 1)):
        raise LifecycleError('activated_socket_invalid')
    socket_acl_absent(path, before)
    nonce = secrets.token_hex(16)
    request = dict(schema_version=BROKER_REQUEST_SCHEMA_VERSION, request_id='finite-readiness-'+nonce,
                   operation='service-readiness', payload={'nonce': nonce})
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(5)
        connection.connect(SOCKET)
        connection.sendall(json.dumps(request, separators=(',', ':')).encode()+b'\n')
        raw = bytearray()
        while len(raw) <= 65536 and not raw.endswith(b'\n'):
            part = connection.recv(min(4096, 65537-len(raw)))
            if not part:
                raise LifecycleError('readiness_response_incomplete')
            raw.extend(part)
        if len(raw) > 65536 or bytes(raw).count(b'\n') != 1:
            raise LifecycleError('readiness_response_invalid')
        response = _strict_json(bytes(raw))
        if (set(response) != {'schema_version', 'request_id', 'operation', 'ok', 'result'}
                or response['schema_version'] != BROKER_RESPONSE_SCHEMA_VERSION
                or response['request_id'] != request['request_id'] or response['operation'] != 'service-readiness'
                or response['ok'] is not True or type(response['result']) is not dict
                or response['result'].get('nonce') != nonce):
            raise LifecycleError('readiness_response_mismatch')
        reply = {key: value for key, value in response['result'].items() if key != 'nonce'}
        # Capture AFTER the server sends, while its readiness-only ACK wait
        # keeps this exact connection alive. Darwin LOCAL_PEERTOKEN follows
        # the peer socket's last process, unlike cached listen credentials.
        peer = bind_live_peer(connection, reply)
        after = path.lstat()
        if socket_identity(before) != socket_identity(after):
            raise LifecycleError('socket_generation_changed')
        socket_acl_absent(path, after)
        _current_capture(peer)
        reply['kernel_peer'] = dict(euid=peer.euid, pid=peer.pid, pidversion=peer.pidversion,
                                    audit_identity_digest=peer.audit_identity_digest)
        connection.sendall(nonce.encode('ascii')+b'\n')
        return reply


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        if (len(args) != 5 or args[0] not in ACTIONS | {'--probe'}
                or args[1] != '--expected-sha' or args[3] != '--expected-manifest-sha256'
                or re.fullmatch(r'[0-9a-f]{40}', args[2]) is None
                or re.fullmatch(r'[0-9a-f]{64}', args[4]) is None
                or not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode):
            raise LifecycleError('fixed_installed_arguments_required')
        if os.geteuid() != (450 if args[0] == '--probe' else 0):
            raise LifecycleError('wrong_caller_principal')
        verify_release_before_import(args[2], args[4])
        if args[0] == '--probe':
            value = probe_socket()
        else:
            value = run_lifecycle(ProductionHost(args[4]), args[0], args[2])
        print(json.dumps(value, sort_keys=True, separators=(',', ':')))
        return 0
    except Exception as exc:
        unknown = isinstance(exc, LifecycleError) and exc.effect_unknown
        print(json.dumps(dict(status='EFFECT_UNKNOWN' if unknown else 'REFUSED',
            code=exc.code if isinstance(exc, LifecycleError) else 'qualification_unavailable'),
            sort_keys=True, separators=(',', ':')))
        return 75 if unknown else 65


if __name__ == '__main__':
    raise SystemExit(main())
