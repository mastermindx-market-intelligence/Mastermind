"""Canonical-paid definition source is inert until the root owners qualify it.

Offline root fixtures and host test doubles cover mechanical transitions
only: synthetic release bytes stand in for the future integrated paid source
package and a mechanical pwd/grp double stands in for the actual UID 501
principal. No live OS principal, root install, launchctl, provider or
network is ever touched and no listener or process is created. The one
unpatched pin-map test asserts the real production raw3 contract directly;
the synthetic fixtures never claim production qualification.
"""
import os
import json
import plistlib
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import canonical_paid_definition as paid
from ops.executive_os.capacity_broker_topology import CONTROL_UID
from control_plane.executive_capacity_join import (
    CapacityJoin,
    PROVIDER_CAPACITY_SCHEMA,
)
from control_plane.executive_fabric_bridge_broker import BridgeConfig, BridgeProtocolError
from control_plane.executive_fabric_composition import _bindings, _document, FabricCompositionError
from control_plane.fabric_attended_routing import (
    FINITE_DEFINITION_DIR,
    FINITE_SOCKET_PATH,
)

SHA = 'b' * 40
TREE = 'c' * 40
HOST = 'host-' + 'a' * 64
CAPABILITY = 'fixture-paid-capacity'
CONTROL_SHA = 'e' * 64
RELEASE_SCHEMA = 'mastermind.executive_release_manifest/v1'
RELEASE_ROOT_TEXT = '/Library/Application Support/MastermindExecutive/releases/' + SHA


def overlay_document(model='glm-5.3-flash'):
    """Closed parent overlay: it deliberately carries no principal claim."""
    return {'schema_version': paid.OVERLAY_SCHEMA, 'adapter_id': paid.ADAPTER_ID,
            'provider': paid.PAID_PROVIDER, 'model': model,
            'http_endpoint': paid.PAID_HTTP_ENDPOINT,
            'execution_profile_sha256': 'd' * 64,
            'permission_profile_sha256': '6' * 64}


def prior_config():
    control = {'proof_base_sha': SHA, 'runtime_root': '/private/var/db/mastermind-executive',
               'ceo_submit_armed': False, 'coo_autonomy_armed': False,
               'coo_operator_harness_armed': False, 'fabric_bridge_armed': False,
               'coo_foreground_only': False}
    worker = {'worker_id': 'codex-01', 'worker_user': '_mastermind_worker',
              'worker_uid': 451, 'worker_gid': 451, 'control_uid': CONTROL_UID,
              'operator_harness_armed': False,
              'provider_home': '/private/var/db/mastermind-executive/workers/codex-01/provider-home'}
    return SimpleNamespace(control=control, worker=worker,
                           control_sha256=CONTROL_SHA, worker_sha256='9' * 64)


class MechanicalPrincipal:
    """Mechanical pwd/grp double for one ordinary actual UID 501 record."""

    def __init__(self, name='chriswong', uid=501, gid=20, group='staff'):
        self.user_record = SimpleNamespace(pw_name=name, pw_uid=uid, pw_gid=gid, pw_dir='/Users/' + name)
        self.reverse_user = SimpleNamespace(pw_name=name, pw_uid=uid, pw_gid=gid, pw_dir='/Users/' + name)
        self.group_record = SimpleNamespace(gr_name=group, gr_gid=gid)
        self.reverse_group = SimpleNamespace(gr_name=group, gr_gid=gid)
        self.user_error = None
        self.reverse_error = None
        self.group_error = None
        self.reverse_group_error = None

    def install(self, monkeypatch):
        principal = self

        def getpwuid(uid):
            if principal.user_error is not None:
                raise principal.user_error
            assert uid == paid.PAID_BRIDGE_UID
            return principal.user_record

        def getpwnam(name):
            if principal.reverse_error is not None:
                raise principal.reverse_error
            assert name == principal.user_record.pw_name
            return principal.reverse_user

        def getgrgid(gid):
            if principal.group_error is not None:
                raise principal.group_error
            assert gid == principal.user_record.pw_gid
            return principal.group_record

        def getgrnam(name):
            if principal.reverse_group_error is not None:
                raise principal.reverse_group_error
            assert name == principal.group_record.gr_name
            return principal.reverse_group

        monkeypatch.setattr(paid.pwd, 'getpwuid', getpwuid)
        monkeypatch.setattr(paid.pwd, 'getpwnam', getpwnam)
        monkeypatch.setattr(paid.grp, 'getgrgid', getgrgid)
        monkeypatch.setattr(paid.grp, 'getgrnam', getgrnam)

    def rebase_user(self, name, uid=501, gid=20):
        """Move the whole emulated principal coherently to another identity."""
        self.user_record = SimpleNamespace(pw_name=name, pw_uid=uid, pw_gid=gid, pw_dir='/Users/' + name)
        self.reverse_user = SimpleNamespace(pw_name=name, pw_uid=uid, pw_gid=gid, pw_dir='/Users/' + name)


def synthetic_release_files():
    """Bounded synthetic release bytes; honest fixtures, never real source."""
    return {
        paid.SHIM_MODULE: b'"""Synthetic paid entrypoint fixture; never executed."""\n',
        paid.CANDIDATE_GLM_SHIM: b'"""Synthetic candidate shim fixture."""\nVALUE = 1\n',
        paid.CANDIDATE_GLM_LEASE_GATEWAY: b'"""Synthetic candidate gateway fixture."""\nVALUE = 2\n',
        paid.CANDIDATE_GLM_LEASE_CAPABILITY: b'"""Synthetic candidate capability fixture."""\nVALUE = 3\n',
        paid.RAW_GLM_SHIM: b'"""Synthetic raw shim preimage fixture."""\n',
        paid.RAW_GLM_LEASE_GATEWAY: b'"""Synthetic raw gateway preimage fixture."""\n',
        paid.RAW_GLM_LEASE_CAPABILITY: b'"""Synthetic raw capability preimage fixture."""\n',
    }


def synthetic_pins(files):
    return {relative: (paid.sha256(files[relative]), len(files[relative]))
            for relative in (paid.RAW_GLM_SHIM, paid.RAW_GLM_LEASE_GATEWAY,
                             paid.RAW_GLM_LEASE_CAPABILITY)}


class FakeRelease:
    """Mechanical installed-release double for the fixed paid source paths."""

    def __init__(self):
        self.files = synthetic_release_files()
        self.default_mode = 0o644
        self.entry_mutations = {}       # original-manifest entry overrides
        self.verify_only_mutations = {}  # divergence seen only by verify()
        self.missing = set()
        self.duplicates = set()
        self.serve_overrides = {}       # bytes served instead of the file
        self.verify_error = None
        self.no_entries = False
        self.manifest_raw = None
        self.reads = []

    def entry(self, relative, mutations=None):
        if relative in self.missing:
            return None
        raw = self.files[relative]
        entry = {'path': relative, 'type': 'file', 'size': len(raw),
                 'sha256': paid.sha256(raw), 'uid': 0, 'gid': 0,
                 'mode': self.default_mode}
        entry.update(self.entry_mutations.get(relative, {}))
        if mutations:
            entry.update(mutations)
        return entry

    def document(self, scope='original'):
        entries = []
        for relative in sorted(self.files):
            mutations = None
            if scope == 'verified':
                mutations = self.verify_only_mutations.get(relative)
            value = self.entry(relative, mutations)
            if value is not None:
                entries.append(value)
        for relative in sorted(self.duplicates):
            entries.append(dict(self.entry(relative)))
        return {'schema_version': RELEASE_SCHEMA, 'commit_sha': SHA,
                'tree_sha': TREE,
                'entries': None if self.no_entries else entries}

    def install(self, monkeypatch):
        release = self

        def read_root_file(path, *, modes, uid=0, gid=None):
            relative = str(Path(path).relative_to(paid._RELEASES_ROOT / SHA))
            release.reads.append(relative)
            assert uid == 0 and gid == 0
            assert relative in paid.RELEASE_SOURCE_PATHS, relative
            assert modes == paid._RELEASE_SOURCE_MODES
            return (release.serve_overrides.get(relative, release.files[relative]),
                    SimpleNamespace(st_mode=stat.S_IFREG | release.default_mode))

        def read_release_manifest(expected_sha):
            assert expected_sha == SHA
            release.reads.append(paid._MANIFEST_NAME)
            return (release.manifest_raw if release.manifest_raw is not None
                    else paid._json(release.document()))

        def verify(root, commit_sha, tree_sha):
            if release.verify_error is not None:
                raise release.verify_error
            assert str(root) == str(paid._RELEASES_ROOT / SHA)
            assert commit_sha == SHA and tree_sha == TREE
            return release.document(scope='verified')

        monkeypatch.setattr(paid.owner, '_read_root_file', read_root_file)
        monkeypatch.setattr(paid.owner, '_release_manifest_bytes', read_release_manifest)
        from ops.executive_os import release_manifest as manifest_owner
        monkeypatch.setattr(manifest_owner, 'verify', verify)

    def supplied_sources(self):
        sources = {name: self.files[relative]
                   for name, relative in paid.BOUND_SOURCE_PATHS.items()}
        sources['overlay'] = paid._json(overlay_document())
        return sources


@pytest.fixture
def harness(monkeypatch):
    """Mechanical root/principal/release doubles around the actual renderer."""
    monkeypatch.setattr(paid.os, 'geteuid', lambda: 0)
    principal = MechanicalPrincipal()
    principal.install(monkeypatch)
    release = FakeRelease()
    release.install(monkeypatch)
    # Synthetic pins for the synthetic tree; the real map is asserted
    # unpatched in test_production_pins_bind_the_original_raw3_preimages.
    monkeypatch.setattr(paid, 'RAW_SOURCE_PINS', synthetic_pins(release.files))
    prior = prior_config()
    sources = release.supplied_sources()

    def render(prior_value=None, sources_value=None, **changes):
        return paid.render_definition(
            prior if prior_value is None else prior_value, SHA,
            host_ref=changes.pop('host_ref', HOST),
            capacity_capability_id=changes.pop('capability', CAPABILITY),
            external_sources=sources if sources_value is None else sources_value,
            **changes)

    return SimpleNamespace(principal=principal, release=release, prior=prior,
                           sources=sources, render=render)


@pytest.fixture
def paid_env(harness):
    """Actual renderer output; only the installed release reads are doubled."""
    artifacts = harness.render()
    join = CapacityJoin(HOST, CAPABILITY, PROVIDER_CAPACITY_SCHEMA,
                        paid.sha256(artifacts['profile.json']))
    return SimpleNamespace(harness=harness, prior=harness.prior, artifacts=artifacts,
                           join=join, sources=harness.sources,
                           manifest_bytes=paid._json(harness.release.document()))


class FakeHost:
    """Mechanical transition double; production verdicts are never impersonated."""

    def __init__(self, prior, actions):
        self.prior = prior
        self.actions = actions

    def require_exact_install(self, sha):
        self.actions.append('install')
        return sha

    def require_transaction_absent(self):
        self.actions.append('transaction-absent')

    def _config_root_safe(self):
        self.actions.append('config-root-safe')

    def require_services_already_stopped(self):
        self.actions.append('services-stopped')

    def require_service_uids_quiescent(self):
        self.actions.append('uids-quiescent')

    def load_unarmed_configs(self, sha):
        self.actions.append('configs-disarmed')
        return self.prior

    def require_runtime_quiescent(self, config):
        self.actions.append('runtime-quiescent')


@pytest.fixture
def locked_publisher(monkeypatch, paid_env, tmp_path):
    home = tmp_path / 'control-config'
    home.mkdir()
    monkeypatch.setattr(paid.owner, 'CONFIG_ROOT', home)
    monkeypatch.setattr(paid, 'DESTINATION', home / paid.PAID_DEFINITION_DIRNAME)
    # The fake-host fixture does not impersonate the root-owned CONFIG_ROOT;
    # real root-trust reproving is separate owner work.
    monkeypatch.setattr(paid, '_trusted_control_root', lambda fd: os.fstat(fd))
    actions = []
    host = FakeHost(paid_env.prior, actions)
    monkeypatch.setattr(paid.owner, 'ProductionCeoSubmitHost', lambda: host)
    writes = []
    real_write = paid._write_exclusive

    def fake_write(directory, payload, *, uid, gid, mode=0o444, parent_fd=None):
        actions.append('publish-exclusive')
        assert not directory.exists()
        writes.append((directory, uid, gid))
        return paid.verify_candidate(payload)

    monkeypatch.setattr(paid, '_write_exclusive', fake_write)
    return SimpleNamespace(actions=actions, writes=writes, home=home, host=host,
                           real_write=real_write)


def _profile(**changes):
    def mutate(artifacts):
        doc = _document(artifacts['profile.json'])
        doc.update(changes)
        return dict(artifacts, **{'profile.json': paid._json(doc)})
    return mutate


def _rebound(**changes):
    def mutate(artifacts):
        doc = _document(artifacts['bindings.json'])
        # Caller-proposed physical facts cannot populate an inert definition.
        doc['bindings'] = [changes]
        return dict(artifacts, **{'bindings.json': paid._json(doc)})
    return mutate


def _replisted(change):
    def mutate(artifacts):
        name = paid.PAID_LABEL + '.plist'
        body = plistlib.loads(artifacts[name])
        change(body)
        return dict(artifacts, **{name: plistlib.dumps(body, fmt=plistlib.FMT_XML,
                                                       sort_keys=True)})
    return mutate


def _redigests(**changes):
    def mutate(artifacts):
        doc = _document(artifacts['profile.json'])
        digests = dict(doc['source_digests'])
        digests.update(changes)
        return _profile(source_digests=digests)(artifacts)
    return mutate


def _rebridge(**changes):
    def mutate(artifacts):
        doc = _document(artifacts['bridge.json'])
        doc.update(changes)
        return dict(artifacts, **{'bridge.json': paid._json(doc)})
    return mutate


def _tamper():
    return [
        ('missing file', lambda a: {k: v for k, v in a.items() if k != 'bindings.json'}),
        ('extra file', lambda a: dict(a, **{'extra.json': b'{}'})),
        ('empty file', lambda a: dict(a, **{'profile.json': b''})),
        ('oversize file', lambda a: dict(a, **{'profile.json': b'x' * 32769})),
        ('foreign plist', lambda a: dict(a, **{paid.PAID_LABEL + '.plist': b'not plist'})),
        ('profile schema drift', _profile(schema_version=paid.PROFILE_SCHEMA + 'x')),
        ('profile extra key', _profile(untrusted_selector='choose-me')),
        ('profile missing key', lambda a: dict(a, **{'profile.json': paid._json(
            {k: v for k, v in _document(a['profile.json']).items() if k != 'host_ref'})})),
        ('profile socket', _profile(socket_path='/var/run/mastermind-executive/other.sock')),
        ('profile socket name', _profile(launchd_socket_name='AttendedFabric')),
        ('profile bridge uid', _profile(bridge_uid=502)),
        ('profile bridge gid control', _profile(bridge_gid=paid.CONTROL_GID)),
        ('profile bridge gid zero', _profile(bridge_gid=0)),
        ('profile bridge gid negative', _profile(bridge_gid=-20)),
        ('profile bridge user reserved', _profile(bridge_user='_mastermind_worker')),
        ('profile bridge user finite prefix', _profile(bridge_user='_mastermind_paid')),
        ('profile bridge user control', _profile(bridge_user='_mastermind_exec')),
        ('profile bridge user unbounded', _profile(bridge_user='bad name!')),
        ('profile bridge group drift', _profile(bridge_group='admin')),
        ('profile bridge group reserved', _profile(bridge_group='_mastermind_worker')),
        ('profile control uid', _profile(control_uid=0)),
        ('profile provider', _profile(provider='minimax')),
        ('profile model', _profile(model='glm-4.7-air')),
        ('profile endpoint', _profile(http_endpoint='http://127.0.0.1:8443')),
        ('profile dynamic python', _profile(
            entrypoint={'python': '/usr/bin/python3', 'shim_module': paid.SHIM_MODULE})),
        ('profile dynamic module', _profile(
            entrypoint={'python': paid.EXECUTABLE_PYTHON, 'shim_module': 'scripts/other.py'})),
        ('profile entrypoint extra', _profile(
            entrypoint={'python': paid.EXECUTABLE_PYTHON, 'shim_module': paid.SHIM_MODULE,
                        'flag': True})),
        ('profile source map missing candidates', _profile(
            source_digests={'shim': '0' * 64, 'overlay': '0' * 64})),
        ('profile source map missing entrypoint', _profile(
            source_digests={name: '0' * 64 for name in paid.EXTERNAL_SOURCES
                            if name != 'shim'})),
        ('profile source map extra entry', _redigests(
            **{'candidate_extra': '0' * 64})),
        ('profile source digest shape', _redigests(**{'shim': 'nothex'})),
        ('profile armed', _profile(bridge_armed=True)),
        ('profile admitted', _profile(capacity_admitted=True)),
        ('profile release', _profile(release_commit='f' * 40)),
        ('profile unbound host', _profile(host_ref='local-unbound')),
        ('profile capability', _profile(capacity_capability_id='../escape')),
        ('bridge frame ceiling', _rebridge(max_request_bytes=1024)),
        ('bridge extra key', _rebridge(untrusted=True)),
        ('binding host', _rebound(host_ref='m2studio')),
        ('binding model', _rebound(model='glm-5.3')),
        ('binding digest', _rebound(worker_source_config_digest='0' * 64)),
        ('binding bridge uid', _rebound(bridge_uid=CONTROL_UID)),
        ('binding worker uid', _rebound(worker_uid=450)),
        ('binding worker gid drift', _rebound(worker_gid=21)),
        ('plist not disabled', _replisted(lambda body: body.update(Disabled=False))),
        ('plist run at load', _replisted(lambda body: body.update(RunAtLoad=True))),
        ('plist dynamic executable', _replisted(
            lambda body: body['ProgramArguments'].__setitem__(0, '/usr/bin/python3'))),
        ('plist label', _replisted(
            lambda body: body.update(Label='com.mastermind.executive.fabric.other'))),
        ('plist socket path', _replisted(
            lambda body: body['Sockets'][paid.PAID_LAUNCHD_SOCKET_NAME]
            .update(SockPathName=FINITE_SOCKET_PATH))),
        ('plist frozen config argument dropped', _replisted(
            lambda body: body['ProgramArguments'].pop())),
        ('plist frozen config flag renamed', _replisted(
            lambda body: body['ProgramArguments'].__setitem__(-2, '--config-file'))),
        ('plist shim entrypoint dropped', _replisted(
            lambda body: body['ProgramArguments'].__setitem__(4, 'scripts/other.py'))),
        ('plist user claim drift', _replisted(
            lambda body: body.update(UserName='_mastermind_paid'))),
        ('plist group claim drift', _replisted(
            lambda body: body.update(GroupName='admin'))),
        ('plist working directory', _replisted(
            lambda body: body.update(WorkingDirectory='/tmp'))),
        ('plist socket group', _replisted(
            lambda body: body['Sockets'][paid.PAID_LAUNCHD_SOCKET_NAME]
            .update(SockPathGroup=20))),
    ]


TAMPER = _tamper()


def test_production_paid_constants_are_frozen(harness):
    # The unpatched module state is asserted directly: real parent pins,
    # frozen entrypoint/config startup facts and the closed source bounds.
    assert paid.PAID_BRIDGE_UID == 501
    assert not hasattr(paid, 'PAID_BRIDGE_GID')
    assert paid.PAID_BRIDGE_CONFIG_PATH == ('/Library/Application Support/'
                                            'MastermindExecutive/config/'
                                            'fabric-glm-paid-01/bridge.json')
    assert str(paid.DESTINATION) == ('/Library/Application Support/MastermindExecutive'
                                     '/config/' + paid.PAID_DEFINITION_DIRNAME)
    assert Path(paid.PAID_BRIDGE_CONFIG_PATH).parent == Path(paid.DESTINATION)
    assert paid.BOUND_SOURCE_PATHS == {
        'shim': 'scripts/executive_paid_fabric_shim.py',
        'candidate_glm_shim': 'ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py',
        'candidate_glm_lease_gateway':
            'ops/native_fabric/paid_canonical_glm/candidate/glm_lease_gateway.py',
        'candidate_glm_lease_capability':
            'ops/native_fabric/paid_canonical_glm/candidate/glm_lease_capability.py',
    }
    assert paid.RELEASE_SOURCE_PATHS == (frozenset(paid.BOUND_SOURCE_PATHS.values())
                                         | frozenset(paid.RAW_SOURCE_PINS))
    assert len(paid.RELEASE_SOURCE_PATHS) == 7
    assert paid.MAX_FILE_BYTES == 32_768
    assert paid.MAX_SOURCE_FILE_BYTES >= 131_072
    assert paid.MAX_SOURCE_TOTAL_BYTES >= paid.MAX_SOURCE_FILE_BYTES
    assert paid.PAID_CONFIG_ARGUMENT == '--config'
    assert paid.EXECUTABLE_PYTHON.endswith('/python3.12')
    assert paid.EXECUTABLE_PYTHON == '/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12'


def test_production_pins_bind_the_original_raw3_preimages():
    """Unpatched exact assertion: the real immutable parent-owned raw3 map."""
    assert paid.RAW_SOURCE_PINS == {
        'ops/native_fabric/paid_canonical_glm/source/glm_shim.py': (
            '020b9ef9c59260d07980a23f2ac277d4e4d7350ff81e010d071fd733cc05b1fc', 65508),
        'ops/native_fabric/paid_canonical_glm/source/glm_lease_gateway.py': (
            '7fd2b64925cb7d7ea83dd37e3802ddab9d004e775bb4ed04e5da04a51dc5ed00', 5843),
        'ops/native_fabric/paid_canonical_glm/source/glm_lease_capability.py': (
            'e80070971fdce507c5314e05b5be67abd0f9cd4603ae6a6b1072e666f3e0a5b7', 9781),
    }


def test_renderer_is_the_only_accepted_four_file_shape(paid_env):
    hashes = paid.verify_candidate(paid_env.artifacts)
    assert set(hashes) == paid.FILES
    assert hashes == {name: paid.sha256(paid_env.artifacts[name]) for name in paid.FILES}
    assert paid.PAID_LABEL + '.plist' in paid_env.artifacts
    from ops.executive_os import finite_definition_publication as finite
    assert paid.FILES != finite.FILES
    assert paid.PAID_LABEL + '.plist' not in finite.FILES
    assert paid.PAID_SOCKET_PATH != FINITE_SOCKET_PATH
    assert str(paid.DESTINATION) != FINITE_DEFINITION_DIR
    assert paid.PAID_BRIDGE_UID not in (CONTROL_UID, 470)


def test_frozen_startup_arguments_bind_entrypoint_and_root_config(paid_env):
    body = plistlib.loads(paid_env.artifacts[paid.PAID_LABEL + '.plist'])
    assert body['ProgramArguments'] == [
        paid.EXECUTABLE_PYTHON, '-I', '-S', '-B',
        RELEASE_ROOT_TEXT + '/' + paid.SHIM_MODULE,
        '--config',
        '/Library/Application Support/MastermindExecutive/config/'
        'fabric-glm-paid-01/bridge.json']
    assert body['WorkingDirectory'] == RELEASE_ROOT_TEXT
    assert body['Disabled'] is True and body['RunAtLoad'] is False
    socket = body['Sockets'][paid.PAID_LAUNCHD_SOCKET_NAME]
    assert socket['SockPathName'] == paid.PAID_SOCKET_PATH
    assert socket['SockPathOwner'] == 0
    assert socket['SockPathGroup'] == 450 and socket['SockPathMode'] == 0o660


def test_sealed_profile_binds_release_sources_principal_and_capacity(paid_env):
    profile = _document(paid_env.artifacts['profile.json'])
    assert profile['release_commit'] == SHA and profile['release_tree'] == TREE
    assert profile['release_manifest_sha256'] == paid.sha256(paid_env.manifest_bytes)
    assert profile['entrypoint'] == {'python': paid.EXECUTABLE_PYTHON,
                                     'shim_module': paid.SHIM_MODULE}
    assert set(profile['source_digests']) == set(paid.EXTERNAL_SOURCES)
    assert profile['source_digests']['shim'] == paid.sha256(paid_env.sources['shim'])
    assert profile['source_digests']['overlay'] == paid.sha256(paid_env.sources['overlay'])
    assert (profile['source_digests']['candidate_glm_shim']
            == paid.sha256(paid_env.sources['candidate_glm_shim']))
    assert profile['provider'] == 'glm' and profile['model'] == 'glm-5.3-flash'
    assert profile['http_endpoint'] == 'http://127.0.0.1:4141'
    assert profile['bridge_armed'] is False and profile['capacity_admitted'] is False
    # Derived actual principal facts, sealed as data.
    assert profile['bridge_uid'] == 501
    assert profile['bridge_user'] == 'chriswong'
    assert profile['bridge_gid'] == 20
    assert profile['bridge_group'] == 'staff'
    assert _document(paid_env.artifacts['bindings.json'])['bindings'] == []
    assert profile['expected_remote_binary'] is None
    assert profile['remote_worker_identity'] is None
    assert profile['bridge_home'] == '/Users/chriswong'
    assert 'provider_home' not in profile
    assert paid_env.join.worker_source_config_digest == paid.sha256(paid_env.artifacts['profile.json'])
    body = plistlib.loads(paid_env.artifacts[paid.PAID_LABEL + '.plist'])
    assert body['UserName'] == 'chriswong' and body['GroupName'] == 'staff'
    bridge = _document(paid_env.artifacts['bridge.json'])
    assert bridge['bridge_uid'] == 501 and bridge['control_uid'] == CONTROL_UID


def test_principal_is_derived_never_invented(paid_env):
    """Positive case: an ordinary actual UID 501 with primary GID 20/staff."""
    assert paid_env.harness.principal.user_record.pw_name == 'chriswong'
    assert _document(paid_env.artifacts['profile.json'])['bridge_gid'] == 20
    assert 'bridge_user' not in paid._PAID_OVERLAY_FIELDS
    assert 'bridge_user' not in paid_env.sources['overlay'].decode()
    assert '501' != str(_document(paid_env.artifacts['profile.json'])['bridge_gid'])


def test_paid_config_schema_is_separate_from_the_closed_legacy_schema(paid_env):
    bridge_document = _document(paid_env.artifacts['bridge.json'])
    with pytest.raises(BridgeProtocolError):
        BridgeConfig.from_document(bridge_document)
    legacy = dict(bridge_document,
                  schema_version='mastermind.executive_fabric_bridge_config/v1',
                  adapter_id='attended-fabric')
    with pytest.raises(paid.CanonicalPaidPublicationRefused):
        paid._validate_paid_bridge_document(legacy)


@pytest.mark.parametrize('label,mutation', TAMPER, ids=[item[0] for item in TAMPER])
def test_tampered_definitions_are_refused_before_any_write(paid_env, label, mutation):
    with pytest.raises(paid.CanonicalPaidPublicationRefused):
        paid.verify_candidate(mutation(paid_env.artifacts))


def test_verify_candidate_is_a_pure_closed_wire_check(paid_env, monkeypatch):
    """Verification seals wire data; it never pretends to authenticate anyone."""
    def refuse(*args, **kwargs):
        raise AssertionError('verification must not consult the principal owners')

    monkeypatch.setattr(paid.pwd, 'getpwuid', refuse)
    monkeypatch.setattr(paid.pwd, 'getpwnam', refuse)
    monkeypatch.setattr(paid.grp, 'getgrgid', refuse)
    monkeypatch.setattr(paid.grp, 'getgrnam', refuse)
    hashes = paid.verify_candidate(paid_env.artifacts)
    assert set(hashes) == paid.FILES
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='reserved or finite'):
        paid.verify_candidate(_profile(bridge_user='_mastermind_nonexistent')(
            paid_env.artifacts))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='derived GID'):
        paid.verify_candidate(_profile(bridge_gid=paid.CONTROL_GID)(paid_env.artifacts))
    # Pure candidate validation bounds DATA; production publication re-renders
    # from the actual pwd/grp owner and refuses any changed principal facts.
    assert paid.verify_candidate(_profile(bridge_gid=501)(paid_env.artifacts))


def _principal_cases():
    def absent(principal):
        principal.user_error = KeyError('no such process')

    def different_uid_record(principal):
        principal.user_record = SimpleNamespace(pw_name='chriswong', pw_uid=502,
                                                pw_gid=20)

    def reversed_uid_drift(principal):
        principal.reverse_user = SimpleNamespace(pw_name='chriswong', pw_uid=502,
                                                 pw_gid=20)

    def reversed_name_drift(principal):
        principal.reverse_user = SimpleNamespace(pw_name='other', pw_uid=501,
                                                 pw_gid=20)

    def reversed_gid_drift(principal):
        principal.reverse_user = SimpleNamespace(pw_name='chriswong', pw_uid=501,
                                                 pw_gid=21)

    def reverse_user_absent(principal):
        principal.reverse_error = KeyError('no such process')

    def group_absent(principal):
        principal.group_error = KeyError('no such process')

    def group_gid_drift(principal):
        principal.group_record = SimpleNamespace(gr_name='staff', gr_gid=21)

    def reversed_group_drift(principal):
        principal.reverse_group = SimpleNamespace(gr_name='staff', gr_gid=21)

    def reverse_group_absent(principal):
        principal.reverse_group_error = KeyError('no such process')

    def reserved_finite_worker(principal):
        principal.rebase_user('_mastermind_worker')

    def nonexistent_finite_name(principal):
        principal.rebase_user('_mastermind_nonexistent')

    def control_user(principal):
        principal.rebase_user('_mastermind_exec')

    def mastermind_group(principal):
        principal.group_record = SimpleNamespace(gr_name='_mastermind_paid', gr_gid=20)

    def control_group(principal):
        principal.rebase_user('chriswong', gid=450)
        principal.group_record = SimpleNamespace(gr_name='_mastermind_exec', gr_gid=450)

    def root_group(principal):
        principal.rebase_user('chriswong', gid=0)
        principal.group_record = SimpleNamespace(gr_name='wheel', gr_gid=0)

    def unbounded_username(principal):
        principal.rebase_user('bad name!')

    def unbounded_group_name(principal):
        principal.group_record = SimpleNamespace(gr_name='', gr_gid=20)

    return [
        ('uid absent', absent, 'unavailable'),
        ('different uid record', different_uid_record, 'fixed UID'),
        ('reverse uid drift', reversed_uid_drift, 'not coherent'),
        ('reverse name drift', reversed_name_drift, 'not coherent'),
        ('reverse gid drift', reversed_gid_drift, 'not coherent'),
        ('reverse user absent', reverse_user_absent, 'does not resolve'),
        ('group absent', group_absent, 'group is unavailable'),
        ('group gid drift', group_gid_drift, 'differs from its GID'),
        ('reverse group drift', reversed_group_drift, 'group is not coherent'),
        ('reverse group absent', reverse_group_absent, 'does not resolve'),
        ('reserved finite worker name', reserved_finite_worker, 'reserved or finite'),
        ('nonexistent finite name', nonexistent_finite_name, 'reserved or finite'),
        ('control user name', control_user, 'reserved or finite'),
        ('mastermind group name', mastermind_group, 'reserved or finite'),
        ('control primary group', control_group, 'must not reuse Control'),
        ('root primary group', root_group, 'must not reuse Control'),
        ('unbounded username', unbounded_username, 'bounded principal name'),
        ('unbounded group name', unbounded_group_name, 'bounded principal name'),
    ]


@pytest.mark.parametrize('label,mutate,expect', _principal_cases(),
                         ids=[item[0] for item in _principal_cases()])
def test_actual_principal_qualification_refuses_drift(harness, label, mutate, expect):
    mutate(harness.principal)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match=expect):
        harness.render()
    assert not (Path('/Library/Application Support/MastermindExecutive/config')
                / paid.PAID_DEFINITION_DIRNAME).exists()


def test_no_caller_supplies_the_bridge_principal(harness):
    """No overlay claim, argument or callback can choose the principal."""
    overlay = dict(_document(harness.sources['overlay']), bridge_user='_mastermind_paid')
    sources = dict(harness.sources, overlay=paid._json(overlay))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='closed schema'):
        harness.render(sources_value=sources)
    profile = _document(harness.render()['profile.json'])
    assert profile['bridge_user'] == 'chriswong'


def test_principal_drift_after_sealing_refuses_locked_publication(locked_publisher,
                                                                  harness):
    sealed = harness.render()
    join = CapacityJoin(HOST, CAPABILITY, PROVIDER_CAPACITY_SCHEMA,
                        paid.sha256(sealed['profile.json']))
    harness.principal.rebase_user('transferred')
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='source-rendered'):
        paid.publish_definition(SHA, CONTROL_SHA, sealed, capacity_join=join,
                                external_sources=harness.sources)
    assert locked_publisher.actions == ['install', 'transaction-absent',
                                        'services-stopped', 'uids-quiescent',
                                        'configs-disarmed', 'runtime-quiescent']
    assert 'publish-exclusive' not in locked_publisher.actions


def test_renderer_requires_root_disarmed_prior_and_exact_release(harness, monkeypatch):
    def attempt(**changes):
        prior = prior_config()
        prior.control.update(changes.pop('control', {}))
        prior.worker.update(changes.pop('worker', {}))
        return harness.render(prior_value=prior, **changes)

    monkeypatch.setattr(paid.os, 'geteuid', lambda: 501)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='sealed root'):
        attempt()
    monkeypatch.setattr(paid.os, 'geteuid', lambda: 0)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='disarmed'):
        attempt(control={'coo_autonomy_armed': True})
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='disarmed'):
        attempt(control={'proof_base_sha': 'a' * 40})
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='disarmed'):
        attempt(worker={'operator_harness_armed': True})
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='release identity'):
        paid.render_definition(harness.prior, 'short', host_ref=HOST,
                               capacity_capability_id=CAPABILITY,
                               external_sources=harness.sources)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='host identity'):
        harness.render(host_ref='m2studio')
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='Capacity identity'):
        harness.render(capability='../escape')
    drifted = paid._json({'commit_sha': 'd' * 40, 'tree_sha': TREE})
    monkeypatch.setattr(paid.owner, '_release_manifest_bytes', lambda sha: drifted)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='manifest differs'):
        attempt()
    from ops.executive_os import release_manifest as manifest_owner
    monkeypatch.setattr(paid.owner, '_release_manifest_bytes',
                        lambda sha: paid._json(harness.release.document()))
    monkeypatch.setattr(manifest_owner, 'verify',
                        lambda *args: (_ for _ in ()).throw(ValueError('tree drift')))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='release tree'):
        attempt()


def test_external_sources_must_be_complete_exact_and_supported(harness):
    def attempt(sources):
        return harness.render(sources_value=sources)

    sources = harness.sources
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='complete exact'):
        attempt(dict(sources, extra=b'x'))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='complete exact'):
        attempt({name: sources[name] for name in sources if name != 'shim'})
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='complete exact'):
        attempt(dict(sources, shim=b''))
    oversize = b'x' * (paid.MAX_SOURCE_FILE_BYTES + 1)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='complete exact'):
        attempt(dict(sources, shim=oversize))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='complete exact'):
        attempt(dict(sources, candidate_glm_shim=oversize))
    for name in sorted(paid.BOUND_SOURCE_PATHS):
        damaged = dict(sources)
        damaged[name] = b'def broken(:\n'
        with pytest.raises(paid.CanonicalPaidPublicationRefused,
                           match='release source is incomplete'):
            attempt(damaged)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='overlay preimage'):
        attempt(dict(sources, overlay=b'not json'))
    secret = overlay_document()
    secret['controller_token'] = 'secret'
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='closed schema'):
        attempt(dict(sources, overlay=paid._json(secret)))
    unsupported = overlay_document(model='gpt-5')
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='provider or model'):
        attempt(dict(sources, overlay=paid._json(unsupported)))
    for model in ('glm-5.3', 'glm-5.3-flash'):
        artifacts = attempt(dict(sources, overlay=paid._json(overlay_document(model))))
        assert _document(artifacts['profile.json'])['model'] == model


def _entry_cases():
    return [(path,) for path in sorted(paid.RELEASE_SOURCE_PATHS)]


@pytest.mark.parametrize('relative', [item[0] for item in _entry_cases()])
def test_release_entries_must_be_exact_unique_regular_root_files(harness, relative):
    def attempt():
        return harness.render()

    harness.release.missing.add(relative)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='one exact entry'):
        attempt()
    harness.release.missing.discard(relative)
    harness.release.duplicates.add(relative)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='one exact entry'):
        attempt()
    harness.release.duplicates.discard(relative)
    digest_expectation = ('immutable parent pin' if relative in paid.RAW_SOURCE_PINS
                          else 'supplied')
    for mutation, expectation in (
            ({'type': 'symlink'}, 'bounded root-owned regular file'),
            ({'mode': 0o664}, 'bounded root-owned regular file'),
            ({'uid': 501}, 'bounded root-owned regular file'),
            ({'gid': 20}, 'bounded root-owned regular file'),
            ({'size': 0}, 'bounded root-owned regular file'),
            ({'sha256': '0' * 64}, digest_expectation),
    ):
        harness.release.entry_mutations[relative] = mutation
        with pytest.raises(paid.CanonicalPaidPublicationRefused, match=expectation):
            attempt()
        del harness.release.entry_mutations[relative]
    assert harness.release.entry_mutations == {}
    harness.render()


@pytest.mark.parametrize('relative', [item[0] for item in _entry_cases()])
def test_installed_bytes_must_equal_the_supplied_preimage(harness, relative):
    harness.release.serve_overrides[relative] = b'drifted installed bytes\n'
    with pytest.raises(paid.CanonicalPaidPublicationRefused):
        harness.render()
    del harness.release.serve_overrides[relative]
    harness.render()


def test_release_entries_must_agree_with_the_original_manifest(harness):
    for relative in sorted(paid.RELEASE_SOURCE_PATHS):
        harness.release.verify_only_mutations[relative] = {'sha256': '1' * 64}
        with pytest.raises(paid.CanonicalPaidPublicationRefused,
                           match='differs from its original manifest'):
            harness.render()
        del harness.release.verify_only_mutations[relative]


def test_release_manifest_entries_shape_is_enforced(harness, monkeypatch):
    harness.release.no_entries = True
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='entries differ'):
        harness.render()
    harness.release.no_entries = False
    from ops.executive_os import release_manifest as manifest_owner
    monkeypatch.setattr(manifest_owner, 'verify',
                        lambda *args: {'commit_sha': SHA, 'tree_sha': TREE})
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='entries differ'):
        harness.render()


def test_candidate_digests_derive_from_the_selected_release(harness, monkeypatch):
    """Candidate digests are parent-owned and move; they are never frozen."""
    previous = _document(harness.render()['profile.json'])['source_digests']
    harness.release.files[paid.CANDIDATE_GLM_SHIM] = (
        b'"""Synthetic candidate shim fixture, second revision."""\nVALUE = 11\n')
    harness.release.files[paid.RAW_GLM_SHIM] = (
        b'"""Synthetic raw shim preimage fixture, second revision."""\n')
    monkey_pins = synthetic_pins(harness.release.files)
    assert monkey_pins != synthetic_pins(synthetic_release_files())
    monkeypatch.setattr(paid, 'RAW_SOURCE_PINS', monkey_pins)
    sources = harness.release.supplied_sources()
    profile = _document(harness.render(sources_value=sources)['profile.json'])
    assert (profile['source_digests']['candidate_glm_shim']
            == paid.sha256(sources['candidate_glm_shim']))
    assert profile['source_digests'] != previous


def test_future_producer_fails_closed_until_the_genuine_release_agrees(monkeypatch):
    """Real unpatched raw3 pins refuse any synthetic release tree."""
    monkeypatch.setattr(paid.os, 'geteuid', lambda: 0)
    MechanicalPrincipal().install(monkeypatch)
    release = FakeRelease()
    release.install(monkeypatch)
    with pytest.raises(paid.CanonicalPaidPublicationRefused,
                       match='immutable parent pin'):
        paid.render_definition(prior_config(), SHA, host_ref=HOST,
                               capacity_capability_id=CAPABILITY,
                               external_sources=release.supplied_sources())
    assert release.reads[-1] == paid.RAW_GLM_LEASE_CAPABILITY
    assert release.reads.count(paid._MANIFEST_NAME) == 1


def test_raw3_pin_drift_refuses(monkeypatch, harness):
    pins = synthetic_pins(harness.release.files)
    first = sorted(pins)[0]
    digest, size = pins[first]
    pins[first] = ('0' * 64, size)
    monkeypatch.setattr(paid, 'RAW_SOURCE_PINS', pins)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='immutable parent pin'):
        harness.render()
    pins[first] = (digest, size + 1)
    monkeypatch.setattr(paid, 'RAW_SOURCE_PINS', pins)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='immutable parent pin'):
        harness.render()


def test_release_reads_stay_on_the_fixed_owner_paths(paid_env):
    reads = paid_env.harness.release.reads
    assert paid._MANIFEST_NAME in reads
    assert set(reads) <= paid.RELEASE_SOURCE_PATHS | {paid._MANIFEST_NAME}
    for relative in sorted(paid.RELEASE_SOURCE_PATHS):
        assert reads.count(relative) >= 1


def test_single_exclusive_publication_preserves_bytes_and_refuses_replay(paid_env, tmp_path):
    destination = tmp_path / paid.PAID_DEFINITION_DIRNAME
    stamp = paid._write_exclusive(destination, paid_env.artifacts,
                                  uid=os.getuid(), gid=os.getgid())
    assert stamp == paid.verify_candidate(paid_env.artifacts)
    assert set(path.name for path in destination.iterdir()) == paid.FILES
    assert (destination.stat().st_mode & 0o777) == 0o755
    assert all((destination / name).read_bytes() == raw
               for name, raw in paid_env.artifacts.items())
    assert all(((destination / name).stat().st_mode & 0o777) == 0o444 for name in paid.FILES)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='already exists'):
        paid._write_exclusive(destination, paid_env.artifacts,
                              uid=os.getuid(), gid=os.getgid())
    assert set(path.name for path in destination.iterdir()) == paid.FILES


def test_destination_symlink_is_never_adopted(paid_env, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    destination = tmp_path / paid.PAID_DEFINITION_DIRNAME
    destination.symlink_to(outside, target_is_directory=True)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='already exists'):
        paid._write_exclusive(destination, paid_env.artifacts,
                              uid=os.getuid(), gid=os.getgid())
    assert list(outside.iterdir()) == []


def test_private_stage_write_error_never_creates_partial_canonical(paid_env, monkeypatch, tmp_path):
    destination = tmp_path / paid.PAID_DEFINITION_DIRNAME
    original = paid.os.fchown
    count = [0]

    def deny_second(fd, uid, gid):
        count[0] += 1
        assert not destination.exists()
        if count[0] == 2:
            raise OSError('test-only simulated incomplete write')
        return original(fd, uid, gid)

    monkeypatch.setattr(paid.os, 'fchown', deny_second)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='without canonical'):
        paid._write_exclusive(destination, paid_env.artifacts,
                              uid=os.getuid(), gid=os.getgid())
    assert not destination.exists()
    assert not list(tmp_path.glob('.' + paid.PAID_DEFINITION_DIRNAME + '.*.stage'))
    monkeypatch.setattr(paid.os, 'fchown', original)
    assert paid._write_exclusive(destination, paid_env.artifacts,
                                 uid=os.getuid(), gid=os.getgid()) == \
        paid.verify_candidate(paid_env.artifacts)


def test_rename_ack_lost_preserves_canonical_and_refuses_second_publish(paid_env, monkeypatch, tmp_path):
    destination = tmp_path / paid.PAID_DEFINITION_DIRNAME
    from ops.executive_os import capacity_host_artifacts as rename_owner

    def issued_then_lost(src_fd, source, dst_fd, target):
        os.rename(source, target, src_dir_fd=src_fd, dst_dir_fd=dst_fd)
        raise OSError('simulated native ack lost after rename')

    monkeypatch.setattr(rename_owner, '_rename_exclusive', issued_then_lost)
    with pytest.raises(paid.CanonicalPaidPublicationEffectUnknown):
        paid._write_exclusive(destination, paid_env.artifacts,
                              uid=os.getuid(), gid=os.getgid())
    assert destination.exists()
    assert set(path.name for path in destination.iterdir()) == paid.FILES
    assert all((destination / name).read_bytes() == raw
               for name, raw in paid_env.artifacts.items())
    assert not list(tmp_path.glob('.' + paid.PAID_DEFINITION_DIRNAME + '.*.stage'))
    monkeypatch.setattr(rename_owner, '_rename_exclusive',
                        lambda *args: (_ for _ in ()).throw(OSError('atomic no-replace refused')))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='already exists'):
        paid._write_exclusive(destination, paid_env.artifacts,
                              uid=os.getuid(), gid=os.getgid())


def test_acl_drift_prevents_canonical_publication(paid_env, monkeypatch, tmp_path):
    from control_plane import fs_security
    monkeypatch.setattr(fs_security, 'has_macos_acl', lambda *args, **kwargs: True)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='without canonical'):
        paid._write_exclusive(tmp_path / paid.PAID_DEFINITION_DIRNAME, paid_env.artifacts,
                              uid=os.getuid(), gid=os.getgid())
    assert not (tmp_path / paid.PAID_DEFINITION_DIRNAME).exists()
    assert not list(tmp_path.glob('.' + paid.PAID_DEFINITION_DIRNAME + '.*.stage'))


def test_prior_private_stage_requires_reconciliation(paid_env, tmp_path):
    stage = tmp_path / ('.' + paid.PAID_DEFINITION_DIRNAME + '.1.deadbeef.stage')
    stage.mkdir()
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(paid.CanonicalPaidPublicationRefused, match='reconciliation'):
            paid._require_definition_absent(descriptor, paid.PAID_DEFINITION_DIRNAME)
    finally:
        os.close(descriptor)


def test_root_owner_publishes_once_after_locked_render_join_and_gates(locked_publisher,
                                                                      paid_env):
    result = paid.publish_definition(SHA, CONTROL_SHA, paid_env.artifacts,
                                     capacity_join=paid_env.join,
                                     external_sources=paid_env.sources)
    actions = locked_publisher.actions
    assert result == {'state': 'STAGED_DISARMED_DEFINITION', 'release': SHA,
                      'control_preimage_sha256': CONTROL_SHA,
                      'artifacts': paid.verify_candidate(paid_env.artifacts),
                      'effect': 'APPLIED', 'admitted_worker': False,
                      'capacity_admitted': False, 'service_started': False}
    assert actions[:6] == ['install', 'transaction-absent', 'services-stopped',
                           'uids-quiescent', 'configs-disarmed', 'runtime-quiescent']
    assert actions[6:8] == ['install', 'transaction-absent']
    assert actions[8] == 'config-root-safe'
    assert actions[9:14] == ['install', 'transaction-absent', 'services-stopped',
                             'uids-quiescent', 'configs-disarmed']
    assert actions.count('install') == 4
    assert actions.index('publish-exclusive') > actions.index('runtime-quiescent')
    assert locked_publisher.writes == [(paid.DESTINATION, 0, 0)]


def test_capacity_join_mismatch_blocks_before_any_owner_action(locked_publisher, paid_env, monkeypatch):
    monkeypatch.setattr(paid, '_write_exclusive',
                        lambda *args, **kwargs: pytest.fail('never publish a foreign join'))
    foreign = CapacityJoin(HOST, 'other-capability', PROVIDER_CAPACITY_SCHEMA,
                           paid.sha256(paid_env.artifacts['profile.json']))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='sealed paid profile'):
        paid.publish_definition(SHA, CONTROL_SHA, paid_env.artifacts,
                                capacity_join=foreign, external_sources=paid_env.sources)
    wrong_digest = CapacityJoin(HOST, CAPABILITY, PROVIDER_CAPACITY_SCHEMA, '0' * 64)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='sealed paid profile'):
        paid.publish_definition(SHA, CONTROL_SHA, paid_env.artifacts,
                                capacity_join=wrong_digest, external_sources=paid_env.sources)
    assert locked_publisher.actions == []


def test_no_caller_boolean_or_callback_is_capacity_permission(locked_publisher, paid_env, monkeypatch):
    monkeypatch.setattr(paid, '_write_exclusive',
                        lambda *args, **kwargs: pytest.fail('no callback permission'))
    for bad in (None, True, lambda join: True):
        with pytest.raises(paid.CanonicalPaidPublicationRefused, match='no caller boolean'):
            paid.publish_definition(SHA, CONTROL_SHA, paid_env.artifacts,
                                    capacity_join=bad, external_sources=paid_env.sources)
    assert locked_publisher.actions == []


def test_live_service_blocks_before_render_or_publish(locked_publisher, paid_env, monkeypatch):
    monkeypatch.setattr(paid, '_write_exclusive',
                        lambda *args, **kwargs: pytest.fail('no publication'))
    monkeypatch.setattr(paid, 'render_definition',
                        lambda *args, **kwargs: pytest.fail('render must not run during live service'))
    locked_publisher.host.require_services_already_stopped = (
        lambda: (_ for _ in ()).throw(ValueError('Control still running')))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='preflight refused'):
        paid.publish_definition(SHA, CONTROL_SHA, paid_env.artifacts,
                                capacity_join=paid_env.join, external_sources=paid_env.sources)
    assert locked_publisher.actions == ['install', 'transaction-absent']


def test_occupied_mutex_is_definite_refusal_before_any_effect(locked_publisher, paid_env, monkeypatch):
    monkeypatch.setattr(paid, '_write_exclusive',
                        lambda *args, **kwargs: pytest.fail('no publication'))
    monkeypatch.setattr(paid.fcntl, 'flock',
                        lambda *args: (_ for _ in ()).throw(BlockingIOError('other owner writing')))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='mutex occupied'):
        paid.publish_definition(SHA, CONTROL_SHA, paid_env.artifacts,
                                capacity_join=paid_env.join, external_sources=paid_env.sources)
    assert 'publish-exclusive' not in locked_publisher.actions


def test_post_publish_config_drift_is_unknown_effect_never_success(locked_publisher, paid_env):
    reads = [0]
    original = locked_publisher.host.load_unarmed_configs

    def drifting(sha):
        reads[0] += 1
        if reads[0] == 3:  # preflight, locked interval, then the postimage read
            return SimpleNamespace(**dict(vars(locked_publisher.host.prior),
                                          worker_sha256='f' * 64))
        return original(sha)

    locked_publisher.host.load_unarmed_configs = drifting
    with pytest.raises(paid.CanonicalPaidPublicationEffectUnknown, match='postimage'):
        paid.publish_definition(SHA, CONTROL_SHA, paid_env.artifacts,
                                capacity_join=paid_env.join, external_sources=paid_env.sources)
    assert reads == [3]
    assert locked_publisher.writes == [(paid.DESTINATION, 0, 0)]


def test_existing_destination_is_inspected_never_republished(locked_publisher, paid_env, monkeypatch):
    destination = locked_publisher.home / paid.PAID_DEFINITION_DIRNAME
    locked_publisher.real_write(destination, paid_env.artifacts,
                                uid=os.getuid(), gid=os.getgid())
    monkeypatch.setattr(paid, '_write_exclusive',
                        lambda *args, **kwargs: pytest.fail('no second publish'))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='already exists'):
        paid.publish_definition(SHA, CONTROL_SHA, paid_env.artifacts,
                                capacity_join=paid_env.join, external_sources=paid_env.sources)
    assert set(path.name for path in destination.iterdir()) == paid.FILES


def test_publish_requires_the_source_rendered_bytes(locked_publisher, paid_env, monkeypatch):
    monkeypatch.setattr(paid, '_write_exclusive',
                        lambda *args, **kwargs: pytest.fail('no publication'))
    overlay = overlay_document(model='glm-5.3')
    other = paid.render_definition(
        paid_env.prior, SHA, host_ref=HOST, capacity_capability_id=CAPABILITY,
        external_sources=dict(paid_env.sources, overlay=paid._json(overlay)))
    other_join = CapacityJoin(HOST, CAPABILITY, PROVIDER_CAPACITY_SCHEMA,
                              paid.sha256(other['profile.json']))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='source-rendered'):
        paid.publish_definition(SHA, CONTROL_SHA, other,
                                capacity_join=other_join, external_sources=paid_env.sources)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='sealed paid profile'):
        paid.publish_definition(SHA, CONTROL_SHA, other,
                                capacity_join=paid_env.join, external_sources=paid_env.sources)
    assert 'publish-exclusive' not in locked_publisher.actions


def test_release_source_drift_inside_the_lock_is_refused(locked_publisher, paid_env):
    """Release bytes rotated after preflight can never publish stale seals."""
    release = paid_env.harness.release
    original = locked_publisher.host.load_unarmed_configs
    rotated = [False]

    def rotate_on_locked_interval(sha):
        result = original(sha)
        if locked_publisher.actions.count('configs-disarmed') == 2 and not rotated[0]:
            rotated[0] = True
            release.files[paid.CANDIDATE_GLM_LEASE_GATEWAY] = (
                b'"""Synthetic candidate gateway fixture, rotated bytes."""\n'
                b'VALUE = 22\n')
        return result

    locked_publisher.host.load_unarmed_configs = rotate_on_locked_interval
    with pytest.raises(paid.CanonicalPaidPublicationRefused,
                       match='supplied'):
        paid.publish_definition(SHA, CONTROL_SHA, paid_env.artifacts,
                                capacity_join=paid_env.join,
                                external_sources=paid_env.sources)
    assert rotated == [True]
    assert 'publish-exclusive' not in locked_publisher.actions


def test_non_root_cannot_render_or_publish(paid_env, monkeypatch):
    monkeypatch.setattr(paid.os, 'geteuid', lambda: 501)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='sealed root'):
        paid.render_definition(paid_env.prior, SHA, host_ref=HOST,
                               capacity_capability_id=CAPABILITY,
                               external_sources=paid_env.sources)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='exact root release'):
        paid.publish_definition(SHA, CONTROL_SHA, paid_env.artifacts,
                                capacity_join=paid_env.join,
                                external_sources=paid_env.sources)


@pytest.mark.parametrize('mutation', [
    _redigests(shim='8' * 64), _profile(host_ref='host-' + 'b' * 64),
])
def test_valid_candidate_data_cannot_replace_original_publication_join(
        paid_env, locked_publisher, mutation):
    damaged = mutation(paid_env.artifacts)
    # Closed candidate DATA is not authenticated host/source evidence.
    assert paid.verify_candidate(damaged)
    with pytest.raises(paid.CanonicalPaidPublicationRefused):
        paid.publish_definition(SHA, CONTROL_SHA, damaged,
                                capacity_join=paid_env.join,
                                external_sources=paid_env.sources)
    assert locked_publisher.writes == []


def test_inert_definition_never_manufactures_remote_execution_identity(paid_env):
    profile = _document(paid_env.artifacts['profile.json'])
    assert profile['expected_remote_binary'] is None
    assert profile['remote_worker_identity'] is None
    assert _document(paid_env.artifacts['bindings.json'])['bindings'] == []
    with pytest.raises(FabricCompositionError):
        _bindings(paid_env.artifacts['bindings.json'])
    for change in ({'expected_remote_binary': {'sha256': profile['source_digests']['shim']}},
                   {'remote_worker_identity': {'uid': 501, 'gid': 20}}):
        with pytest.raises(paid.CanonicalPaidPublicationRefused, match='unavailable'):
            paid.verify_candidate(_profile(**change)(paid_env.artifacts))


def test_controller_home_and_bounded_wire_contract_are_exact(paid_env):
    profile = _document(paid_env.artifacts['profile.json'])
    plist = plistlib.loads(paid_env.artifacts[paid.PAID_LABEL + '.plist'])
    assert profile['bridge_home'] == '/Users/chriswong'
    assert plist['EnvironmentVariables']['HOME'] == '/Users/chriswong'
    assert 'provider_home' not in profile
    bridge = _document(paid_env.artifacts['bridge.json'])
    assert bridge['max_request_bytes'] == 1048576
    assert bridge['max_response_bytes'] == 4194304
    assert bridge['request_timeout_seconds'] == 3600
    for change in ({'max_request_bytes': 65536}, {'max_response_bytes': 262144},
                   {'request_timeout_seconds': 30}):
        with pytest.raises(paid.CanonicalPaidPublicationRefused):
            paid.verify_candidate(_rebridge(**change)(paid_env.artifacts))


@pytest.mark.parametrize('home', ['', 'relative', '/Users/../root', '/Users/x\x00'])
def test_actual_bridge_home_must_be_bounded_absolute_metadata(paid_env, home):
    principal = paid_env.harness.principal
    principal.user_record.pw_dir = home
    principal.reverse_user.pw_dir = home
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='home'):
        paid.render_definition(paid_env.prior, SHA, host_ref=HOST,
                               capacity_capability_id=CAPABILITY,
                               external_sources=paid_env.sources)


def test_actual_bridge_home_drift_stops_locked_publication(paid_env, locked_publisher):
    paid_env.harness.principal.reverse_user.pw_dir = '/Users/different'
    with pytest.raises(paid.CanonicalPaidPublicationRefused):
        paid.publish_definition(SHA, CONTROL_SHA, paid_env.artifacts,
                                capacity_join=paid_env.join,
                                external_sources=paid_env.sources)
    assert locked_publisher.writes == []


def test_source_digest_candidate_cannot_bypass_installed_source_by_rebinding_join(
        paid_env, locked_publisher):
    damaged = _redigests(candidate_glm_shim='0' * 64)(paid_env.artifacts)
    altered_join = CapacityJoin(HOST, CAPABILITY, PROVIDER_CAPACITY_SCHEMA,
                               paid.sha256(damaged['profile.json']))
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='differs'):
        paid.publish_definition(SHA, CONTROL_SHA, damaged,
                                capacity_join=altered_join,
                                external_sources=paid_env.sources)
    assert locked_publisher.writes == []


def test_actual_prepare_action_derives_overlay_from_selected_policy_and_renders(harness,monkeypatch):
    from ops.executive_os import canonical_paid_actions as actions
    from control_plane import paid_model_execution_contract as contract
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    from pathlib import Path
    from ops.native_fabric.quota_continuity.candidate import paid_host_qualification as qualifier
    root=Path(__file__).resolve().parents[1]
    actual=actions._source_overlay
    overlay=actual(root)
    document=json.loads(overlay)
    registry=ExecutionCapabilityRegistry.load(root/'config/executive_agent_capabilities.json',source_root=root)
    assert document['execution_profile_sha256']==registry.resolve(contract.PROFILE_ID).profile_digest
    assert document['permission_profile_sha256']==contract.digest(contract.POLICY)
    class SourceHost:
        def __getattr__(self,name):
            if name.startswith('require_'):return lambda *args:None
            raise AttributeError(name)
        def load_unarmed_configs(self,sha):assert sha==SHA;return harness.prior
    monkeypatch.setattr(actions.owner,'ProductionCeoSubmitHost',SourceHost)
    monkeypatch.setattr(actions,'_source_overlay',lambda release:overlay)
    monkeypatch.setattr(qualifier,'_read_owned',lambda *a,**k:(json.dumps({'raw':{'ssh_alias':'alias'}}).encode(),None))
    published=[]
    def publish(sha,control,artifacts,**kwargs):
        assert sha==SHA and control==CONTROL_SHA
        paid.verify_candidate(artifacts)
        profile=json.loads(artifacts['profile.json'])
        assert profile['execution_profile_sha256']==document['execution_profile_sha256']
        assert profile['permission_profile_sha256']==document['permission_profile_sha256']
        assert profile['bridge_armed'] is False and profile['expected_remote_binary'] is None
        assert kwargs['external_sources']['overlay']==overlay
        published.append(artifacts)
        return {'source_only':True}
    monkeypatch.setattr(paid,'publish_definition',publish)
    assert actions.prepare_paid(SHA,CONTROL_SHA,transport_host='raw',capacity_id=CAPABILITY)=={'source_only':True}
    assert len(published)==1


def test_large_manifest_profile_hash_binds_original_bytes_not_reserialization(harness):
    canonical = paid._json(harness.release.document())
    original = canonical + b" " * (1059792 - len(canonical))
    assert paid.owner._MAX_JSON_BYTES < len(original) < paid.owner._GATEWAY_ROOT_FILE_MAX_BYTES
    assert paid.sha256(original) != paid.sha256(canonical)
    harness.release.manifest_raw = original
    profile = _document(harness.render()['profile.json'])
    assert profile['release_manifest_sha256'] == paid.sha256(original)
    assert profile['release_manifest_sha256'] != paid.sha256(paid._json(_document(original)))
    assert harness.release.reads.count(paid._MANIFEST_NAME) == 1


def test_manifest_capture_refusal_does_not_fall_back_to_generic_or_reserialize(harness, monkeypatch):
    calls = []
    def refused(expected_sha):
        calls.append(expected_sha)
        raise paid.owner.HostControlError('config_identity_unavailable')
    monkeypatch.setattr(paid.owner, '_release_manifest_bytes', refused)
    with pytest.raises(paid.CanonicalPaidPublicationRefused, match='manifest is unavailable'):
        harness.render()
    assert calls == [SHA]
    assert harness.release.reads == []
