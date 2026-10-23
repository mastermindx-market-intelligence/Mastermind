"""Offline mechanical fixtures for the canonical paid qualification source.

Synthetic release bytes, a mechanical root-reader/service-host double, a
mechanical pwd/grp double and a scratch registry stand in for the actual root
install, UID 501 principal and fixed hosts registry. The Bridge qualifier
module is loaded from the real repository qualifier source copied into the
scratch release; its opaque qualify/consume path stays the actual
implementation and only its private transport/snapshot/principal helpers are
mechanical doubles, so a forged observation can never pass the real consume.
Qualifier sources come from the retained candidate/ rollout directory, never
by editing raw source preimages; the transport double launches one real
harmless cross-platform child so the _POPEN_TYPE seal stays exercised. No
fixture claims production identity, live qualification or admission.
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
import plistlib
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import control_plane.fs_security as fs_security
import control_plane.paid_model_execution_contract as contract
from control_plane.executive_fabric_bridge_broker import (
    BridgeConfig,
    BridgeProtocolError,
)
from ops.executive_os import autonomy_control as owner
from ops.executive_os import canonical_paid_definition as base
from ops.executive_os import canonical_paid_qualification as qual
from ops.executive_os import release_manifest as manifest_owner

SHA = 'b' * 40
TREE = 'c' * 40
CONTROL_SHA = 'e' * 64
WORKER_SHA = '9' * 64
HOST_KEY = 'glm-lane-a'
ALIAS = 'lane-glm-a'
CAPABILITY = 'fixture-paid-capacity'
EXECUTION_DIGEST = 'd' * 64
PERMISSION_DIGEST = '6' * 64
PYTHON_PATH = '/usr/bin/python3'
QUALIFIER_DIR = (Path(base.__file__).resolve().parents[2]
                 / 'ops/native_fabric/quota_continuity/candidate')
QUALIFIER_EXT = 'ops/native_fabric/quota_continuity/rollout/native-code-stage/ext'
SELF_RELATIVE = 'ops/executive_os/canonical_paid_qualification.py'



def digest_raw(raw):
    return hashlib.sha256(raw).hexdigest()



def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode()



def overlay_document():
    return {'schema_version': base.OVERLAY_SCHEMA, 'adapter_id': base.ADAPTER_ID,
            'provider': base.PAID_PROVIDER, 'model': qual.PAID_MODEL,
            'http_endpoint': base.PAID_HTTP_ENDPOINT,
            'execution_profile_sha256': EXECUTION_DIGEST,
            'permission_profile_sha256': PERMISSION_DIGEST}



def release_files():
    return {
        base.SHIM_MODULE: b'"""Synthetic paid entrypoint fixture."""\n',
        base.CANDIDATE_GLM_SHIM: b'"""Synthetic candidate shim."""\nVALUE = 1\n',
        base.CANDIDATE_GLM_LEASE_GATEWAY: b'"""Synthetic gateway."""\nVALUE = 2\n',
        base.CANDIDATE_GLM_LEASE_CAPABILITY: b'"""Synthetic capability."""\nVALUE = 3\n',
        base.RAW_GLM_SHIM: b'"""Synthetic raw shim."""\n',
        base.RAW_GLM_LEASE_GATEWAY: b'"""Synthetic raw gateway."""\n',
        base.RAW_GLM_LEASE_CAPABILITY: b'"""Synthetic raw capability."""\n',
    }



def v1_profile_files(release, manifest_raw):
    source_digests = {name: digest_raw((release / relative).read_bytes())
                      for name, relative in base.BOUND_SOURCE_PATHS.items()}
    source_digests['overlay'] = digest_raw(canonical(overlay_document()))
    profile = {
        'schema_version': base.PROFILE_SCHEMA, 'profile_id': base.PROFILE_ID,
        'label': base.PAID_LABEL, 'worker_id': base.WORKER_ID,
        'bridge_uid': base.PAID_BRIDGE_UID, 'bridge_gid': 20,
        'bridge_group': 'staff', 'bridge_user': 'chriswong',
        'bridge_home': '/Users/chriswong', 'control_uid': 450, 'control_gid': 450,
        'launchd_socket_name': base.PAID_LAUNCHD_SOCKET_NAME,
        'socket_path': base.PAID_SOCKET_PATH, 'provider': base.PAID_PROVIDER,
        'model': qual.PAID_MODEL, 'http_endpoint': base.PAID_HTTP_ENDPOINT,
        'host_ref': 'host-' + 'a' * 64, 'release_commit': SHA,
        'release_tree': TREE, 'release_manifest_sha256': digest_raw(manifest_raw),
        'entrypoint': {'python': str(base.EXECUTABLE_PYTHON),
                       'shim_module': base.SHIM_MODULE},
        'source_digests': source_digests,
        'execution_profile_sha256': EXECUTION_DIGEST,
        'permission_profile_sha256': PERMISSION_DIGEST,
        'workspace_root': base.PAID_WORKSPACE_ROOT, 'run_root': base.PAID_RUN_ROOT,
        'expected_remote_binary': None, 'remote_worker_identity': None,
        'capacity_capability_id': CAPABILITY, 'bridge_armed': False,
        'capacity_admitted': False,
    }
    base._validate_paid_profile_document(profile)
    artifacts = {
        'profile.json': canonical(profile),
        'bridge.json': canonical(qual._expected_bridge_document()),
        'bindings.json': canonical({'schema_version': base.BINDINGS_SCHEMA_VERSION,
                                    'bindings': []}),
        base.PAID_LABEL + '.plist': plistlib.dumps(
            base._expected_plist(profile), fmt=plistlib.FMT_XML, sort_keys=True),
    }
    return profile, artifacts



def build_release(scratch):
    release = scratch / 'releases' / SHA
    files = release_files()
    for name in sorted(qual.QUALIFIER_SOURCE_NAMES):
        files[QUALIFIER_EXT + '/' + name] = (QUALIFIER_DIR / name).read_bytes()
    files[SELF_RELATIVE] = Path(qual.__file__).read_bytes()
    entries = [{'path': relative, 'type': 'file', 'size': len(raw),
                'sha256': digest_raw(raw), 'uid': 0, 'gid': 0, 'mode': 0o644}
               for relative, raw in sorted(files.items())]
    manifest_raw = canonical({'schema_version':
                              'mastermind.executive_release_manifest/v1',
                              'commit_sha': SHA, 'tree_sha': TREE,
                              'entries': entries})
    for relative, raw in files.items():
        path = release / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (release / base._MANIFEST_NAME).write_bytes(manifest_raw)
    return release, manifest_raw, files



class MechanicalHost:
    """Recording service/config double; no lifecycle or process effect."""

    def __init__(self):
        self.calls = []
        self.control = {'proof_base_sha': SHA,
                        'runtime_root': '/private/var/db/mastermind',
                        'ceo_submit_armed': False, 'coo_autonomy_armed': False,
                        'coo_operator_harness_armed': False,
                        'fabric_bridge_armed': False,
                        'coo_foreground_only': False}
        self.worker = {'worker_id': 'codex-01',
                       'worker_user': '_mastermind_worker',
                       'worker_uid': 451, 'worker_gid': 451,
                       'control_uid': 450, 'operator_harness_armed': False}
        self.loaded = False
        self.sabotage = {}

    def _note(self, name):
        self.calls.append(name)

    def require_exact_install(self, sha):
        self._note('require_exact_install')
        return sha

    def require_transaction_absent(self):
        self._note('require_transaction_absent')

    def _config_root_safe(self):
        self._note('_config_root_safe')

    def require_services_already_stopped(self):
        self._note('require_services_already_stopped')

    def require_service_uids_quiescent(self):
        self._note('require_service_uids_quiescent')

    def load_unarmed_configs(self, sha):
        self._note('load_unarmed_configs')
        self.sabotage.get('load_unarmed_configs', lambda: None)()
        return SimpleNamespace(control=self.control, worker=self.worker,
                               control_sha256=CONTROL_SHA, worker_sha256=WORKER_SHA)

    def require_runtime_quiescent(self, config):
        self._note('require_runtime_quiescent')
        self.sabotage.get('require_runtime_quiescent', lambda: None)()

    def _loaded_observe_only(self, label):
        self._note('_loaded_observe_only:' + label)
        return self.loaded



def mechanical_reader(counter):
    def read_root_file(path, *, modes, uid=0, gid=None):
        counter.append(str(path))
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            info = os.fstat(descriptor)
            assert stat.S_ISREG(info.st_mode)
            raw = b''
            while True:
                part = os.read(descriptor, 65536)
                if not part:
                    break
                raw += part
            return raw, info
        finally:
            os.close(descriptor)
    return read_root_file



def mechanical_atomic(path, payload, *, mode, uid, gid, replace):
    assert replace is False
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, 'O_NOFOLLOW', 0), mode)
    try:
        view = memoryview(payload)
        while view:
            view = view[os.write(descriptor, view):]
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)



def install_principal(monkeypatch):
    user = SimpleNamespace(pw_name='chriswong', pw_uid=base.PAID_BRIDGE_UID,
                           pw_gid=20, pw_dir='/Users/chriswong')
    group = SimpleNamespace(gr_name='staff', gr_gid=20)
    monkeypatch.setattr(base.pwd, 'getpwuid', lambda uid: user)
    monkeypatch.setattr(base.pwd, 'getpwnam', lambda name: user)
    monkeypatch.setattr(base.grp, 'getgrgid', lambda gid: group)
    monkeypatch.setattr(base.grp, 'getgrnam', lambda name: group)



def observation_document(request):
    lane = str(Path(request['capture_root']).parent.parent)
    binary = {'path': request['python_path'], 'real_path': request['python_path'],
              'version': '3.12.0 (mechanical fixture)',
              'sha256': digest_raw(b'mechanical-python'),
              'team_identifier': None, 'size': 12345, 'device': 1, 'inode': 42,
              'mode': 0o100555, 'uid': 0, 'gid': 0, 'mtime_ns': 1}
    return {'schema': 'mastermind.paid_host_observation/v1', 'request': request,
            'binary': binary, 'worker_uid': 501, 'worker_gid': 20,
            'worker_user': 'chriswong',
            'boot_id': str(uuid.UUID(int=0x12345678123456781234567812345678)),
            'capture_root': request['capture_root'],
            'capture_identity': {'device': 1, 'inode': 7, 'mode': 0o040700,
                                 'uid': 501, 'gid': 20, 'mtime_ns': 5},
            'context_identity': {
                'profile': 'canonical-paid-physical-owner.v1',
                'host_env_path': lane + '/ext/HOST_ENV.sh',
                'host_env_sha256': digest_raw(b'HOST_ENV'),
                'kernel_executable': request['python_path'], 'lane_root': lane}}



def load_qualifier_module(ext_dir):
    spec = importlib.util.spec_from_file_location(
        '_test_paid_qualifier_bridge', ext_dir / 'paid_host_qualification.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def make_swap(recorder, fail):
    def swap(old_fd, old_name, new_fd, new_name, flags):
        recorder.append((old_name, new_name, flags))
        if fail is not None and fail['swap']:
            return -1
        parent = Path(qual.DESTINATION).parent
        temporary = parent / ('.' + qual.DESTINATION.name + '.exchange-tmp')
        os.rename(parent / os.fsdecode(old_name), temporary)
        os.rename(parent / os.fsdecode(new_name), parent / os.fsdecode(old_name))
        os.rename(temporary, parent / os.fsdecode(new_name))
        return 0
    return swap



def fire_on_call(env, name, index, action):
    """Run action() during the index-th mechanical host gate of one attempt."""
    calls = {'n': 0}
    host = env.host
    real = getattr(host, name)

    def wrapper(*args, **kwargs):
        calls['n'] += 1
        if calls['n'] == index:
            action()
        return real(*args, **kwargs)

    setattr(host, name, wrapper)
    return calls



@pytest.fixture
def env(tmp_path, monkeypatch):
    scratch = tmp_path / 'Library' / 'Application Support' / 'MastermindExecutive'
    config_root = scratch / 'config'
    release, manifest_raw, files = build_release(scratch)
    destination = config_root / base.PAID_DEFINITION_DIRNAME
    staging = config_root / (base.PAID_DEFINITION_DIRNAME + '.initial-qualification')
    _profile, artifacts = v1_profile_files(release, manifest_raw)
    destination.mkdir(parents=True)
    os.chmod(config_root, 0o755)
    os.chmod(destination, 0o755)
    for name, raw in artifacts.items():
        (destination / name).write_bytes(raw)
    digests = {name: digest_raw(raw) for name, raw in sorted(artifacts.items())}
    # The frozen preimage: the wire digest (no trailing newline).
    aggregate = contract.digest(digests)
    registry = tmp_path / 'hosts.json'
    registry.write_bytes(canonical({
        HOST_KEY: {'ssh_alias': ALIAS, 'roles': ['lanes'], 'local': None,
                   'platform': 'linux', 'allowed_modes': ['glm'],
                   'qualification_only_modes': []}}))
    registry_sha = digest_raw(registry.read_bytes())
    # Synthetic pins for the synthetic tree, mirroring the retained-previous-
    # result contract; the real pin map is untouched production DATA.
    monkeypatch.setattr(base, 'RAW_SOURCE_PINS', {
        relative: (digest_raw(files[relative]), len(files[relative]))
        for relative in (base.RAW_GLM_SHIM, base.RAW_GLM_LEASE_GATEWAY,
                         base.RAW_GLM_LEASE_CAPABILITY)})
    monkeypatch.setattr(owner, 'SYSTEM_ROOT', scratch)
    monkeypatch.setattr(owner, 'CONFIG_ROOT', config_root)
    monkeypatch.setattr(qual, 'DESTINATION', destination)
    monkeypatch.setattr(qual, 'STAGING', staging)
    monkeypatch.setattr(qual, 'PAID_REGISTRY_NAMESPACE', str(registry))
    monkeypatch.setattr(contract, 'PAID_REGISTRY_NAMESPACE', str(registry))
    monkeypatch.setattr(base, '_trusted_control_root', lambda fd: None)
    monkeypatch.setattr(fs_security, 'has_macos_acl', lambda *a, **k: False)
    monkeypatch.setattr(manifest_owner, 'verify',
                        lambda root, commit, tree: {'entries': json.loads(
                            manifest_raw)['entries']})
    install_principal(monkeypatch)
    monkeypatch.setattr(os, 'geteuid', lambda: 0)
    monkeypatch.setattr(os, 'getuid', lambda: 0)
    monkeypatch.setattr(os, 'chown', lambda path, uid, gid: None)
    real_lstat = os.lstat
    real_stat = os.stat

    def scratch_stat(path, *args, **kwargs):
        # pathlib Path.lstat() resolves through os.stat(follow_symlinks=False),
        # so both entries report the mechanical root:wheel view.
        follow = kwargs.pop('follow_symlinks', True)
        info = real_stat(path, *args, **kwargs) if follow else real_lstat(path, *args, **kwargs)
        if str(os.fspath(path)).startswith(str(tmp_path)):
            fields = list(info)
            fields[4], fields[5] = 0, 0
            info = os.stat_result(fields)
        return info

    monkeypatch.setattr(os, 'lstat', scratch_stat)
    monkeypatch.setattr(os, 'stat', scratch_stat)
    monkeypatch.setattr(owner, '_fsync_directory', lambda path: None)
    reads = []
    monkeypatch.setattr(owner, '_read_root_file', mechanical_reader(reads))
    monkeypatch.setattr(owner, '_atomic_file', mechanical_atomic)
    host = MechanicalHost()
    monkeypatch.setattr(owner, 'ProductionCeoSubmitHost', lambda: host)
    monkeypatch.setattr(qual, '_production_entry_verified', lambda sha: None)
    swap_calls = []
    fail = {'swap': False}
    monkeypatch.setattr(qual, '_resolve_rename_swap',
                        lambda: make_swap(swap_calls, fail))
    loaded = load_qualifier_module(release / QUALIFIER_EXT)
    monkeypatch.setattr(loaded, '_transport_principal', lambda: {
        'uid': 501, 'gid': 20, 'user': 'chriswong', 'home': '/Users/chriswong'})
    snapshot = {'sources': {name: {'sha256': digest, 'identity': (1, 2)}
                            for name, digest in sorted(
                                {source: digest_raw(files[QUALIFIER_EXT + '/' + source])
                                 for source in qual.QUALIFIER_SOURCE_NAMES}.items())},
                'registry_sha256': registry_sha, 'registry_identity': (1, 2),
                'alias': ALIAS}
    monkeypatch.setattr(loaded, '_snapshot',
                        lambda hosts_path, host_ref, expected: snapshot)
    counts = {'qualify': 0, 'consume': 0}
    real_qualify = loaded.qualify_paid_host
    real_consume = loaded.consume_paid_host_qualification

    def owned_transport(request, principal):
        # One real harmless child on any platform; still a real Popen seal.
        child = subprocess.Popen([sys.executable, '-c', 'pass'])
        child.wait()
        return loaded._canonical(observation_document(request)), child

    def counting_qualify(**kwargs):
        counts['qualify'] += 1
        return real_qualify(**kwargs)

    def counting_consume(value, **kwargs):
        counts['consume'] += 1
        return real_consume(value, **kwargs)

    def scratch_owned_read(path, *, owners, maximum=2 * 1024 * 1024):
        if str(path) == str(registry):
            descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            try:
                raw = b''
                while True:
                    part = os.read(descriptor, 65536)
                    if not part:
                        break
                    raw += part
                return raw, os.fstat(descriptor)
            finally:
                os.close(descriptor)
        return loaded._read_owned(path, owners=owners, maximum=maximum)

    monkeypatch.setattr(loaded, '_owned_transport', owned_transport)
    real_transport = owned_transport
    monkeypatch.setattr(loaded, 'qualify_paid_host', counting_qualify)
    monkeypatch.setattr(loaded, 'consume_paid_host_qualification', counting_consume)
    monkeypatch.setattr(loaded, '_read_owned', scratch_owned_read)
    real_loader = qual._load_qualifier
    monkeypatch.setattr(qual, '_load_qualifier', lambda ext_dir, verified: loaded)
    return SimpleNamespace(
        real_loader=real_loader, reads=reads,
        scratch=scratch, config_root=config_root, release=release,
        destination=destination, staging=staging, original=artifacts,
        digests=digests, aggregate=aggregate, registry=registry,
        registry_sha=registry_sha, host=host, counts=counts,
        swap_calls=swap_calls, fail=fail, loaded=loaded, files=files,
        snapshot=snapshot, real_transport=real_transport)


QUALIFY_KWARGS = dict(transport_host=HOST_KEY, python_path=PYTHON_PATH,
                      worker_id=base.WORKER_ID, quota_class='standard',
                      account_label='acct-01')



def capture_root(tmp_path):
    return str(tmp_path / 'lane' / 'ext' / 'lanes')



def run_publish(env, tmp_path, **overrides):
    kwargs = dict(QUALIFY_KWARGS)
    kwargs['capture_root'] = capture_root(tmp_path)
    kwargs.update(overrides)
    return qual.qualify_and_publish(SHA, CONTROL_SHA, env.aggregate, **kwargs)



def probe_request(env, tmp_path):
    return {'schema': 'mastermind.paid_host_probe_request/v1',
            'host_ref': HOST_KEY, 'transport_alias': ALIAS, 'nonce': 'n' * 64,
            'python_path': PYTHON_PATH, 'capture_root': capture_root(tmp_path),
            'release_sha': SHA,
            'source_manifest_sha256': digest_raw(
                (env.release / base._MANIFEST_NAME).read_bytes()),
            'preimage_sha256': env.aggregate,
            'registry_sha256': env.registry_sha,
            'sources_sha256': {name: digest_raw(env.files[QUALIFIER_EXT + '/' + name])
                               for name in sorted(qual.QUALIFIER_SOURCE_NAMES)},
            'probe_sha256': digest_raw(env.loaded._REMOTE_PROBE.encode()),
            'context': 'canonical-paid-physical-owner.v1'}



def v2_artifacts(env, tmp_path):
    """Synthetic v2 bundle from the occupied v1 fixture and one fixture observation."""
    profile = json.loads((env.destination / 'profile.json').read_bytes())
    observation = observation_document(probe_request(env, tmp_path))
    registration = {'worker_id': base.WORKER_ID, 'quota_class': 'standard',
                    'account_label': 'acct-01'}
    composed = dict(profile)
    composed['schema_version'] = qual.PROFILE_SCHEMA_V2
    composed['host_ref'] = contract.paid_host_reference(HOST_KEY, ALIAS)
    composed['expected_remote_binary'] = dict(observation['binary'])
    composed['remote_worker_identity'] = {
        'worker_uid': observation['worker_uid'],
        'worker_gid': observation['worker_gid'],
        'worker_user': observation['worker_user']}
    composed['registration'] = registration
    physical, source = qual._paid_source_document(composed, observation, registration)
    row = {'physical_binding': physical, 'source_config': source,
           'quota_class': 'standard'}
    bindings = canonical({'schema_version': qual.BINDINGS_DOC_SCHEMA,
                          'bindings': [row]})
    composed['bindings_sha256'] = digest_raw(bindings)
    return {'profile.json': canonical(composed),
            'bridge.json': canonical(qual._expected_bridge_document()),
            'bindings.json': bindings,
            base.PAID_LABEL + '.plist': (env.destination / (
                base.PAID_LABEL + '.plist')).read_bytes()}



def test_pure_v2_wire_accepts_and_v1_verifier_rejects(env, tmp_path):
    artifacts = v2_artifacts(env, tmp_path)
    result = qual.verify_qualified_artifacts(artifacts)
    assert result['profile']['schema_version'] == qual.PROFILE_SCHEMA_V2
    assert len(result['bindings']) == 1
    assert result['bindings'][0]['source_config']['model'] == qual.PAID_MODEL
    assert result['profile']['bridge_armed'] is False
    assert result['profile']['capacity_admitted'] is False
    assert result['hashes'] == {name: digest_raw(artifacts[name])
                                for name in sorted(base.FILES)}
    with pytest.raises(base.CanonicalPaidPublicationRefused):
        base.verify_candidate(artifacts)



def test_v2_pure_verifier_enforces_fixed_identity_and_policy_joins(env, tmp_path):
    artifacts = v2_artifacts(env, tmp_path)
    assert qual.verify_qualified_artifacts(artifacts)['profile'] == json.loads(
        artifacts['profile.json'])
    changes = {'schema_version': 'unrecognized/v99', 'profile_id': 'forged',
               'control_uid': 999, 'control_gid': 999, 'bridge_gid': True,
               'permission_profile_sha256': '7' * 64,
               'execution_profile_sha256': 'e' * 63 + 'f', 'provider': 'openai',
               'workspace_root': '/private/var/db/other'}
    for key, replacement in changes.items():
        profile = json.loads(artifacts['profile.json'])
        profile[key] = replacement
        broken = dict(artifacts)
        broken['profile.json'] = canonical(profile)
        with pytest.raises(qual.CanonicalPaidQualificationRefused):
            qual.verify_qualified_artifacts(broken)
    profile = json.loads(artifacts['profile.json'])
    profile['entrypoint']['python'] = '/usr/bin/pythonX'
    broken = dict(artifacts)
    broken['profile.json'] = canonical(profile)
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        qual.verify_qualified_artifacts(broken)



def test_v2_strict_schema_and_registration_refusals(env, tmp_path):
    artifacts = v2_artifacts(env, tmp_path)
    profile = json.loads(artifacts['profile.json'])
    mutations = (
        lambda value: value.update(extra=1),
        lambda value: value.pop('registration'),
        lambda value: value['registration'].update(worker_id='other-01'),
        lambda value: value['registration'].update(quota_class=True),
        lambda value: value.update(bindings_sha256='0' * 64),
        lambda value: value.update(host_ref='host-' + 'f' * 64),
        lambda value: value['expected_remote_binary'].update(size=True),
        lambda value: value['expected_remote_binary'].update(team_identifier='X'),
        lambda value: value.update(remote_worker_identity={'worker_uid': 501}),
        lambda value: value.update(bridge_armed=True),
        lambda value: value.update(model='glm-5.3'),
    )
    for mutation in mutations:
        value = json.loads(canonical(profile))
        mutation(value)
        broken = dict(artifacts)
        broken['profile.json'] = canonical(value)
        with pytest.raises(qual.CanonicalPaidQualificationRefused):
            qual.verify_qualified_artifacts(broken)
    row = json.loads(artifacts['bindings.json'])['bindings'][0]
    row['quota_class'] = 'other-class'
    broken = dict(artifacts)
    broken['bindings.json'] = canonical(
        {'schema_version': qual.BINDINGS_DOC_SCHEMA, 'bindings': [row]})
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        qual.verify_qualified_artifacts(broken)
    broken = dict(artifacts)
    broken['profile.json'] = b'{"schema_version": "x", "schema_version": "y"}'
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        qual.verify_qualified_artifacts(broken)



def test_occupied_bundle_corruption_refused_before_qualification(env, tmp_path):
    names = ('bridge.json', base.PAID_LABEL + '.plist', 'bindings.json')
    originals = {name: (env.destination / name).read_bytes() for name in names}
    corrupt = {
        'bridge.json': canonical({'schema_version': 'other/v1'}),
        base.PAID_LABEL + '.plist': b'<plist><dict broken',
        'bindings.json': canonical({'schema_version': base.BINDINGS_SCHEMA_VERSION,
                                    'bindings': [{'row': 1}]}),
    }
    for name, raw in corrupt.items():
        (env.destination / name).write_bytes(raw)
        with pytest.raises(qual.CanonicalPaidQualificationRefused):
            run_publish(env, tmp_path)
        assert env.counts == {'qualify': 0, 'consume': 0}
        assert not env.staging.exists()
        (env.destination / name).write_bytes(originals[name])
    run_publish(env, tmp_path)



def test_published_bytes_round_trip_with_unchanged_config_plist(env, tmp_path):
    result = run_publish(env, tmp_path)
    artifacts = {name: (env.destination / name).read_bytes()
                 for name in sorted(base.FILES)}
    verified = qual.verify_qualified_artifacts(artifacts)
    assert verified['hashes'] == result['artifacts']
    assert artifacts['bridge.json'] == canonical(qual._expected_bridge_document())
    with pytest.raises(BridgeProtocolError):
        BridgeConfig.from_document(json.loads(artifacts['bridge.json']))
    plist = plistlib.loads(artifacts[base.PAID_LABEL + '.plist'])
    assert (plist['Disabled'] is True and plist['RunAtLoad'] is False
            and plist['KeepAlive'] is False)
    assert result['identity_reference']['bindings_path'] == str(
        env.destination / 'bindings.json')
    assert result['identity_reference']['bindings_sha256'] == digest_raw(
        artifacts['bindings.json'])



def test_happy_path_qualifies_once_publishes_disabled_with_swapped_inodes(
        env, tmp_path):
    before = {name: (env.destination / name).read_bytes()
              for name in sorted(base.FILES)}
    original_ino = env.destination.lstat().st_ino
    result = run_publish(env, tmp_path)
    assert env.counts == {'qualify': 1, 'consume': 1}
    assert len(env.swap_calls) == 1 and env.swap_calls[0][2] == 0x2
    assert (result['effect'] == 'APPLIED' and result['admitted_worker'] is False
            and result['capacity_admitted'] is False
            and result['bridge_armed'] is False
            and result['service_started'] is False
            and result['readiness'] == 'OFFLINE_NOT_ADMITTED')
    assert result['definition_preimage_sha256'] == env.aggregate
    assert result['control_preimage_sha256'] == CONTROL_SHA
    published = {name: (env.destination / name).read_bytes()
                 for name in sorted(base.FILES)}
    assert published['profile.json'] != before['profile.json']
    assert published['bridge.json'] == before['bridge.json']
    assert (published[base.PAID_LABEL + '.plist']
            == before[base.PAID_LABEL + '.plist'])
    assert env.destination.lstat().st_ino != original_ino
    assert env.staging.is_dir()
    archived = {name: (env.staging / name).read_bytes()
                for name in sorted(base.FILES)}
    assert archived == before
    assert any(call.startswith('_loaded_observe_only:')
               for call in env.host.calls)
    profile = json.loads(published['profile.json'])
    assert profile['host_ref'] == contract.paid_host_reference(HOST_KEY, ALIAS)
    assert profile['registration'] == {'worker_id': base.WORKER_ID,
                                       'quota_class': 'standard',
                                       'account_label': 'acct-01'}



def test_signature_has_no_caller_boolean_or_factory_surface():
    parameters = inspect.signature(qual.qualify_and_publish).parameters
    assert set(parameters) == {
        'expected_release_sha', 'expected_control_sha256',
        'expected_definition_sha256', 'transport_host', 'python_path',
        'capture_root', 'worker_id', 'quota_class', 'account_label'}



def test_raw_inputs_validated_before_any_effect(env, tmp_path):
    for overrides in ({'transport_host': ''}, {'transport_host': 'bad key'},
                      {'capture_root': '/tmp'}, {'capture_root': '/x/lanes'},
                      {'python_path': 'relative/python'},
                      {'worker_id': 'other'}, {'quota_class': ''},
                      {'account_label': None}):
        with pytest.raises(qual.CanonicalPaidQualificationRefused):
            run_publish(env, tmp_path, **overrides)
    assert env.counts == {'qualify': 0, 'consume': 0}
    assert not env.staging.exists()



def test_caller_identity_syntax_validated_before_entry_gates(env, tmp_path):
    for arguments in (('short', CONTROL_SHA, env.aggregate),
                      (SHA, 'nothex', env.aggregate),
                      (SHA, CONTROL_SHA, 'z' * 64)):
        with pytest.raises(qual.CanonicalPaidQualificationRefused):
            qual.qualify_and_publish(*arguments, **QUALIFY_KWARGS,
                                     capture_root=capture_root(tmp_path))
    assert env.counts == {'qualify': 0, 'consume': 0}



def test_production_entry_requires_explicit_no_site_isolation_and_pin(
        tmp_path, monkeypatch):
    monkeypatch.setattr(owner, 'SYSTEM_ROOT', tmp_path)
    pinned = tmp_path / 'releases' / SHA / SELF_RELATIVE
    monkeypatch.setattr(os, 'geteuid', lambda: 0)
    monkeypatch.setattr(os, 'getuid', lambda: 0)

    def entry(isolated=True, no_site=True, platform='darwin',
              dont_write_bytecode=True):
        return SimpleNamespace(flags=SimpleNamespace(isolated=isolated,
                                                     no_site=no_site),
                               platform=platform,
                               dont_write_bytecode=dont_write_bytecode)

    monkeypatch.setattr(qual, 'sys', entry())
    monkeypatch.setattr(qual, '__file__', str(pinned))
    qual._production_entry_verified(SHA)
    for kwargs in ({'isolated': False}, {'no_site': False},
                   {'platform': 'linux'}, {'dont_write_bytecode': False}):
        monkeypatch.setattr(qual, 'sys', entry(**kwargs))
        with pytest.raises(qual.CanonicalPaidQualificationRefused):
            qual._production_entry_verified(SHA)
    monkeypatch.setattr(qual, 'sys', entry())
    monkeypatch.setattr(qual, '__file__', '/elsewhere/' + SELF_RELATIVE)
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        qual._production_entry_verified(SHA)
    monkeypatch.setattr(os, 'geteuid', lambda: 501)
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        qual._production_entry_verified(SHA)



def test_definition_preimage_is_the_exact_wire_digest(env, tmp_path):
    assert env.aggregate == contract.digest(env.digests)
    assert env.aggregate != digest_raw(canonical(env.digests))
    wrong = contract.digest(dict(env.digests, **{'profile.json': '0' * 64}))
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        qual.qualify_and_publish(SHA, CONTROL_SHA, wrong, **QUALIFY_KWARGS,
                                 capture_root=capture_root(tmp_path))
    assert env.counts == {'qualify': 0, 'consume': 0}



def test_stale_definition_preimage_refused_before_any_effect(env, tmp_path):
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        qual.qualify_and_publish(SHA, CONTROL_SHA, '0' * 64, **QUALIFY_KWARGS,
                                 capture_root=capture_root(tmp_path))
    assert env.counts == {'qualify': 0, 'consume': 0}
    assert not env.staging.exists()



def test_control_preimage_and_disarm_drift_refused(env, tmp_path):
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        qual.qualify_and_publish(SHA, '1' * 64, env.aggregate, **QUALIFY_KWARGS,
                                 capture_root=capture_root(tmp_path))
    env.host.control['coo_autonomy_armed'] = True
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        run_publish(env, tmp_path)
    env.host.control['coo_autonomy_armed'] = False
    env.host.worker['operator_harness_armed'] = True
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        run_publish(env, tmp_path)
    assert env.counts == {'qualify': 0, 'consume': 0}
    assert not env.staging.exists()



def test_loaded_paid_label_refused(env, tmp_path):
    env.host.loaded = True
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        run_publish(env, tmp_path)
    env.host.loaded = False
    socket = tmp_path / 'paid.sock'
    socket.write_bytes(b'')
    monkey_socket = socket
    real_socket = base.PAID_SOCKET_PATH
    import ops.executive_os.canonical_paid_definition as base_module
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(base_module, 'PAID_SOCKET_PATH', str(monkey_socket))
        with pytest.raises(qual.CanonicalPaidQualificationRefused):
            run_publish(env, tmp_path)
    assert real_socket != str(monkey_socket)
    assert env.counts == {'qualify': 0, 'consume': 0}



def test_occupied_staging_sibling_refused_before_any_read(env, tmp_path):
    env.staging.mkdir(parents=True)
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        run_publish(env, tmp_path)
    assert env.counts == {'qualify': 0, 'consume': 0}
    assert set(os.listdir(env.staging)) == set()
    assert env.reads == []



def test_v2_retry_refused(env, tmp_path):
    profile = json.loads((env.destination / 'profile.json').read_bytes())
    profile['schema_version'] = qual.PROFILE_SCHEMA_V2
    (env.destination / 'profile.json').write_bytes(canonical(profile))
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        run_publish(env, tmp_path)
    assert env.counts == {'qualify': 0, 'consume': 0}
    assert not env.staging.exists()



def test_registry_and_alias_drift_refused(env, tmp_path, monkeypatch):
    def drifting_transport(request, principal):
        raw, child = env.real_transport(request, principal)
        env.registry.write_bytes(env.registry.read_bytes() + b'\n')
        return raw, child

    monkeypatch.setattr(env.loaded, '_owned_transport', drifting_transport)
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        run_publish(env, tmp_path)
    assert env.counts == {'qualify': 1, 'consume': 1}
    assert not env.staging.exists()
    monkeypatch.setattr(env.loaded, '_owned_transport', env.real_transport)
    monkeypatch.setattr(env.loaded, '_snapshot',
                        lambda hosts_path, host_ref, expected: dict(
                            env.snapshot, alias='other-alias'))
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        run_publish(env, tmp_path)
    assert env.counts == {'qualify': 2, 'consume': 2}



def test_ext_source_drift_refused_then_recovers(env, tmp_path):
    target = env.release / QUALIFIER_EXT / 'remote_sub.sh'
    original = target.read_bytes()
    target.write_bytes(original + b'# drift\n')
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        run_publish(env, tmp_path)
    assert env.counts == {'qualify': 0, 'consume': 0}
    target.write_bytes(original)
    run_publish(env, tmp_path)



def test_canonical_definition_race_refused_before_stage(env, tmp_path):
    original = (env.destination / 'profile.json').read_bytes()
    state = {'fired': False}

    def sabotage():
        if not state['fired']:
            state['fired'] = True
            (env.destination / 'profile.json').write_bytes(original + b'\n')

    env.host.sabotage['load_unarmed_configs'] = sabotage
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        run_publish(env, tmp_path)
    assert not env.staging.exists()
    assert env.counts == {'qualify': 0, 'consume': 0}
    (env.destination / 'profile.json').write_bytes(original)



def _drift(env, monkeypatch, kind):
    """One mechanical drift injection, returned as (host gate, action)."""
    other = SimpleNamespace(pw_name='otheruser', pw_uid=base.PAID_BRIDGE_UID,
                            pw_gid=20, pw_dir='/Users/otheruser')
    if kind == 'principal':
        def principal():
            monkeypatch.setattr(base.pwd, 'getpwuid', lambda uid: other)
            monkeypatch.setattr(base.pwd, 'getpwnam', lambda name: other)
        return 'require_exact_install', principal
    if kind == 'stage':
        def substitute():
            (env.staging / 'bindings.json').unlink()
            (env.staging / 'bindings.json').write_bytes(b'{"substituted": true}')
        return 'require_exact_install', substitute
    if kind == 'trusted_root':
        seen = {'n': 0}

        def moving_root(fd):
            seen['n'] += 1
            if seen['n'] == 5:
                raise base.CanonicalPaidPublicationRefused('config root moved')

        monkeypatch.setattr(base, '_trusted_control_root', moving_root)
        return 'require_exact_install', lambda: None

    def gate_failure():
        raise OSError('mechanical ' + kind + ' drift')

    simple = {
        'worker': lambda: env.host.worker.update(operator_harness_armed=True),
        'config': lambda: env.host.control.update(fabric_bridge_armed=True),
        'registry': lambda: env.registry.write_bytes(
            env.registry.read_bytes() + b'\n'),
        'release_source': lambda: (env.release / QUALIFIER_EXT
                                   / 'remote_sub.sh').write_bytes(
            (env.release / QUALIFIER_EXT / 'remote_sub.sh').read_bytes()
            + b'# drift\n'),
    }
    if kind in simple:
        return 'require_exact_install', simple[kind]
    return ('require_services_already_stopped' if kind == 'service'
            else 'require_runtime_quiescent'), gate_failure


@pytest.mark.parametrize('kind', ['worker', 'config', 'principal', 'registry',
                                  'release_source', 'stage'])
def test_drift_after_staging_refused_before_swap(env, tmp_path, monkeypatch,
                                                 kind):
    gate, action = _drift(env, monkeypatch, kind)
    fire_on_call(env, gate, 4, action)
    with pytest.raises(qual.CanonicalPaidQualificationEffectUnknown):
        run_publish(env, tmp_path)
    assert env.swap_calls == []
    assert ((env.destination / 'profile.json').read_bytes()
            == env.original['profile.json'])
    assert env.staging.is_dir()
    if kind == 'stage':
        assert ((env.staging / 'bindings.json').read_bytes()
                == b'{"substituted": true}')



@pytest.mark.parametrize('kind', ['config', 'service', 'runtime', 'principal',
                                  'registry', 'release_source', 'trusted_root'])
def test_post_swap_drift_refused_and_retained(env, tmp_path, monkeypatch, kind):
    gate, action = _drift(env, monkeypatch, kind)
    fire_on_call(env, gate, 5, action)
    with pytest.raises(qual.CanonicalPaidQualificationEffectUnknown):
        run_publish(env, tmp_path)
    assert len(env.swap_calls) == 1
    assert json.loads((env.destination / 'profile.json').read_bytes())[
        'schema_version'] == qual.PROFILE_SCHEMA_V2
    assert ((env.staging / 'bindings.json').read_bytes()
            == env.original['bindings.json'])



def test_partial_stage_failure_retains_residue_as_unknown(env, tmp_path, monkeypatch):
    real_atomic = owner._atomic_file
    state = {'count': 0}

    def failing_atomic(path, payload, **kwargs):
        state['count'] += 1
        if state['count'] == 2:
            raise OSError('mechanical short write')
        return real_atomic(path, payload, **kwargs)

    monkeypatch.setattr(owner, '_atomic_file', failing_atomic)
    with pytest.raises(qual.CanonicalPaidQualificationEffectUnknown):
        run_publish(env, tmp_path)
    assert env.staging.exists() and env.destination.is_dir()
    assert set(os.listdir(env.staging)) == {'bindings.json'}
    assert not (env.staging / (base.PAID_LABEL + '.plist')).exists()
    assert ((env.destination / 'profile.json').read_bytes()
            == env.original['profile.json'])
    assert env.swap_calls == []



def test_failed_swap_retains_residue_as_unknown(env, tmp_path):
    env.fail['swap'] = True
    with pytest.raises(qual.CanonicalPaidQualificationEffectUnknown):
        run_publish(env, tmp_path)
    assert len(env.swap_calls) == 1
    assert env.staging.exists() and env.destination.is_dir()
    assert ((env.destination / 'profile.json').read_bytes()
            == env.original['profile.json'])
    assert json.loads((env.destination / 'profile.json').read_bytes())[
        'schema_version'] == base.PROFILE_SCHEMA



def test_uncertain_postimage_retains_residue_as_unknown(env, tmp_path, monkeypatch):
    reader = owner._read_root_file
    real_swap_factory = qual._resolve_rename_swap
    state = {'swapped': False}

    def tampering_reader(path, *, modes, uid=0, gid=None):
        raw, info = reader(path, modes=modes, uid=uid, gid=gid)
        if (state['swapped'] and Path(path).parent == env.destination
                and Path(path).name == 'bindings.json'):
            raw = raw + b'\n'
        return raw, info

    def noting_factory():
        inner = real_swap_factory()

        def wrapper(*args, **kwargs):
            state['swapped'] = True
            return inner(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(owner, '_read_root_file', tampering_reader)
    monkeypatch.setattr(qual, '_resolve_rename_swap', noting_factory)
    with pytest.raises(qual.CanonicalPaidQualificationEffectUnknown):
        run_publish(env, tmp_path)
    assert env.staging.exists() and env.destination.is_dir()
    assert len(env.swap_calls) == 1
    archived = {name: (env.staging / name).read_bytes()
                for name in sorted(base.FILES)}
    assert archived == env.original



def test_forged_observation_cannot_pass_real_opaque_consume(env, tmp_path):
    """The actual Bridge consume refuses dicts, stale and replayed results."""
    request = probe_request(env, tmp_path)
    consume = env.loaded.consume_paid_host_qualification
    binding = dict(host_ref=HOST_KEY, hosts_path=str(env.registry),
                   release_sha=SHA,
                   source_manifest_sha256=request['source_manifest_sha256'],
                   preimage_sha256=env.aggregate,
                   expected_sources=dict(request['sources_sha256']))
    with pytest.raises(env.loaded.QualificationRefused):
        consume(observation_document(request), **binding)
    observed = env.loaded.qualify_paid_host(python_path=PYTHON_PATH,
                                            capture_root=capture_root(tmp_path),
                                            **binding)
    first = consume(observed, **binding)
    observed_request = dict(first['request'])
    nonce = observed_request.pop('nonce')
    assert nonce != request['nonce'] and len(nonce) == 64
    assert observed_request == {key: value for key, value in request.items()
                                if key != 'nonce'}
    with pytest.raises(env.loaded.QualificationRefused):
        consume(observed, **binding)
    with pytest.raises(env.loaded.QualificationRefused):
        consume(observed, host_ref='other-key', hosts_path=binding['hosts_path'],
                release_sha=SHA,
                source_manifest_sha256=binding['source_manifest_sha256'],
                preimage_sha256=env.aggregate,
                expected_sources=dict(request['sources_sha256']))



def test_qualifier_loader_binds_actual_file_under_selected_ext(env):
    ext_dir = env.release / QUALIFIER_EXT
    loaded = env.real_loader(
        ext_dir, digest_raw((ext_dir / 'paid_host_qualification.py').read_bytes()))
    assert Path(loaded.__file__) == ext_dir / 'paid_host_qualification.py'
    assert frozenset(loaded.SOURCE_NAMES) == qual.QUALIFIER_SOURCE_NAMES
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        env.real_loader(ext_dir, '0' * 64)



def test_qualifier_loader_executes_only_verified_bytes(env, tmp_path):
    assert QUALIFIER_DIR.name == 'candidate'
    assert all((QUALIFIER_DIR / n).is_file() for n in qual.QUALIFIER_SOURCE_NAMES)
    ext = tmp_path / 'loader-ext'
    ext.mkdir()
    good = (env.release / QUALIFIER_EXT / 'paid_host_qualification.py').read_bytes()
    target = ext / qual.QUALIFIER_MODULE_NAME
    sentinel = tmp_path / 'sentinel-marker'
    marker = ("import pathlib\npathlib.Path(%r).write_text('executed')\n"
              % str(sentinel)).encode()
    target.write_bytes(marker)
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        env.real_loader(ext, digest_raw(good))
    assert not sentinel.exists() and not (ext / '__pycache__').exists()
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        env.real_loader(ext, digest_raw(marker))
    assert sentinel.exists()
    target.write_bytes(good)
    module = env.real_loader(ext, digest_raw(good))
    assert Path(module.__file__) == target
    assert frozenset(module.SOURCE_NAMES) == qual.QUALIFIER_SOURCE_NAMES
    sentinel.unlink()
    target.write_bytes(marker)
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        env.real_loader(ext, digest_raw(good))
    assert not sentinel.exists() and not (ext / '__pycache__').exists()



def test_no_cleanup_or_replay_after_unknown(env, tmp_path):
    env.fail['swap'] = True
    with pytest.raises(qual.CanonicalPaidQualificationEffectUnknown):
        run_publish(env, tmp_path)
    staging_names = set(os.listdir(env.staging))
    assert staging_names == set(base.FILES)
    with pytest.raises(qual.CanonicalPaidQualificationRefused):
        run_publish(env, tmp_path)
    assert set(os.listdir(env.staging)) == staging_names
