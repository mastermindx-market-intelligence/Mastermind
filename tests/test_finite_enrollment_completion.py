"""Inert canonical composition and original-effect preservation, no host grants."""
from contextlib import contextmanager
import copy
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest

from ops.executive_os import finite_enrollment_completion as completion
from ops.executive_os.attended_worker_definition import build_finite_worker_artifacts, build_finite_control_delta
from tests.test_attended_worker_definition import inputs


@pytest.fixture
def original(inputs, monkeypatch):
    monkeypatch.setattr('ops.executive_os.finite_reference_assignment.secrets.token_hex',
                        lambda _: pytest.fail('completion must never regenerate references'))
    inputs.update(worker_id='minimax-finite-01', worker_user='_mastermind_minimax',
        worker_group='_mastermind_minimax', worker_uid=470, worker_gid=470,
        runtime_root='/private/var/db/mastermind-executive',
        definition_dir=str(completion.DEFINITION), socket_path=completion.SOCKET,
        host_ref='host-'+'1'*64, capacity_capability_id='fixture.minimax',
        native_capacity_enrollment={
            'schema_version':'mastermind.native_subscription_capacity_enrollment/v1',
            'host_ref':'host-'+'1'*64, 'os_principal_ref':'principal-'+'2'*64,
            'config_custody_ref':'custody-'+'3'*64, 'enrollment_state':'unenrolled',
            'registration_source':{'release_commit':'a'*40, 'previous_release_commit':'b'*40,
                'material_source_digest':'c'*64, 'export_sha256':'d'*64}})
    return build_finite_worker_artifacts(**inputs), inputs


def test_candidate_preserves_references_source_generation_and_closed_control_delta(original):
    artifacts, inputs = original
    preimage = copy.deepcopy(original)
    target = completion.prepare_completion(artifacts, inputs)
    worker = json.loads(target['worker.json'])
    prior = json.loads(artifacts['worker.json'])
    prior['native_capacity_enrollment']['enrollment_state'] = 'enrolled'
    assert worker == prior
    assert original == preimage
    delta = build_finite_control_delta(definition_dir=str(completion.DEFINITION), worker_artifacts=target)
    assert delta['fabric_bridge_armed'] is False
    assert delta['fabric_bindings_sha256'] == hashlib.sha256(target['bindings.json']).hexdigest()
    assert target['bridge.json'] == artifacts['bridge.json']
    assert target[completion.LABEL+'.plist'] == artifacts[completion.LABEL+'.plist']
    scope = {'__name__':'inert_entry_test'}
    exec(compile(target['owner_entry.py'], 'inert', 'exec'), scope)
    assert scope['ARGUMENTS']['bindings_sha256'] == delta['fabric_bindings_sha256']
    assert 'provider_auth' not in worker and worker['operator_harness_armed'] is False


@pytest.mark.parametrize('name', sorted(completion.NAMES))
def test_every_original_file_must_match_canonical_producer(original, name):
    artifacts, inputs = original
    artifacts = dict(artifacts)
    artifacts[name] += b' '
    with pytest.raises(Exception):
        completion.prepare_completion(artifacts, inputs)


@pytest.mark.parametrize('edge', ['enrolled','generation2','foreign-host','foreign-user',
    'foreign-binary','changed-source','changed-root','changed-turn-budget','extra-file','missing-file'])
def test_no_reenrollment_rebinding_or_partial_inventory(original, edge):
    artifacts, inputs = copy.deepcopy(original)
    if edge == 'enrolled': inputs['native_capacity_enrollment']['enrollment_state'] = 'enrolled'
    if edge == 'generation2': inputs['realm_generation'] = 2
    if edge in {'enrolled','generation2'}:
        artifacts = build_finite_worker_artifacts(**inputs)
    if edge == 'foreign-host': inputs['host_ref'] = 'host-'+'4'*64
    if edge == 'foreign-user': inputs['worker_user'] = 'foreign'
    if edge == 'foreign-binary': inputs['binary_receipt_sha256'] = 'e'*64
    if edge == 'changed-source': inputs['native_capacity_enrollment']['registration_source']['export_sha256'] = 'e'*64
    if edge == 'changed-root': inputs['routing_root_id'] = 'foreign'
    if edge == 'changed-turn-budget': inputs['max_turns'] = 3
    if edge == 'extra-file': artifacts['extra.json'] = b'{}'
    if edge == 'missing-file': del artifacts['bridge.json']
    with pytest.raises(Exception):
        completion.prepare_completion(artifacts, inputs)


class FakeHost:
    def __init__(self, original, fail=None):
        self.original, self.inputs = original
        self.calls = []
        self.fail = fail
        self.checks = 0
        self.staged = False

    def event(self, name):
        self.calls.append(name)
        if name == self.fail:
            raise RuntimeError('injected boundary failure')

    @contextmanager
    def interval(self):
        self.event('lock')
        try: yield
        finally: self.calls.append('unlock')

    def snapshot(self):
        self.event('snapshot')
        return {'fixture':True}, self.original, self.inputs

    def require_staging_absent(self):
        self.event('absent')
        if self.staged: raise RuntimeError('retained original effect')

    def recheck(self, *_):
        self.checks += 1
        self.event('recheck'+str(self.checks))

    def stage(self, _):
        self.staged = True
        self.event('stage')

    def verify_staged(self, _): self.event('verify_staged')
    def exchange(self): self.event('exchange')
    def verify_published(self, *_): self.event('verify_published')


def test_one_exchange_after_complete_checks_returns_no_provider_readiness(original):
    host = FakeHost(original)
    result = completion.execute_completion(host)
    assert host.calls == ['lock','snapshot','absent','recheck1','stage','recheck2',
                          'verify_staged','exchange','verify_published','unlock']
    assert result['state'] == 'ENROLLED'
    assert {result[k] for k in ('provider_auth','provider_health','provider_quota')} == {'UNKNOWN'}
    assert not any(result[k] for k in ('service_started','control_selected','runtime_admission'))


@pytest.mark.parametrize('fail', ['lock','snapshot','absent','recheck1','stage',
                                 'recheck2','verify_staged','exchange','verify_published'])
def test_failure_never_retries_rolls_back_or_cleans_original_effect(original, fail):
    host = FakeHost(original, fail)
    with pytest.raises(completion.EnrollmentCompletionError) as result:
        completion.execute_completion(host)
    effect = fail in {'stage','recheck2','verify_staged','exchange','verify_published'}
    assert result.value.effect_unknown is effect
    assert host.calls.count('exchange') <= 1 and host.calls.count('stage') <= 1
    assert host.staged is effect
    assert not {'retry','cleanup','rollback','activate'}.intersection(host.calls)
    if effect:
        host.fail = None
        with pytest.raises(completion.EnrollmentCompletionError):
            completion.execute_completion(host)
        assert host.calls.count('stage') == 1


def test_nonroot_entry_refuses_before_any_config_read(monkeypatch):
    monkeypatch.setattr(completion.os, 'geteuid', lambda:501)
    monkeypatch.setattr(completion.owner.ProductionCeoSubmitHost, '_config_root_safe',
                        lambda _:pytest.fail('nonroot reached config'))
    host = completion.ProductionCompletionHost(expected_sha='a'*40, manifest_sha256='b'*64,
        original_artifact_sha256={name:'c'*64 for name in completion.NAMES})
    with pytest.raises(completion.EnrollmentCompletionError):
        with host.interval(): pytest.fail('nonroot admitted')


@pytest.mark.skipif(sys.platform != 'darwin', reason='Darwin atomic directory primitive')
def test_actual_darwin_directory_exchange_keeps_both_complete_generations(tmp_path, monkeypatch):
    # Real syscall, disposable user-owned fixture directories; no root/app path.
    selected = tmp_path/'selected'; staged = tmp_path/'staged'
    selected.mkdir(); staged.mkdir()
    for name in completion.NAMES:
        (selected/name).write_text('old '+name)
        (staged/name).write_text('new '+name)
    old_inode, new_inode = selected.stat().st_ino, staged.stat().st_ino
    monkeypatch.setattr(completion, 'DEFINITION', selected)
    monkeypatch.setattr(completion, 'STAGING', staged)
    host = completion.ProductionCompletionHost(expected_sha='a'*40, manifest_sha256='b'*64,
        original_artifact_sha256={name:'c'*64 for name in completion.NAMES})
    monkeypatch.setattr(host, '_require_same_config_root', lambda:None)
    libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    host._swap = libc.renameatx_np
    host._swap.argtypes = [ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    host._swap.restype = ctypes.c_int
    host._original_identity = completion._identity(selected.stat())
    host._staged_identity = completion._identity(staged.stat())
    host.fd = os.open(tmp_path, os.O_RDONLY|os.O_DIRECTORY)
    try: host.exchange()
    finally: os.close(host.fd)
    assert selected.stat().st_ino == new_inode and staged.stat().st_ino == old_inode
    assert all((selected/name).read_text() == 'new '+name for name in completion.NAMES)
    assert all((staged/name).read_text() == 'old '+name for name in completion.NAMES)


def test_exchange_refuses_replaced_definition_inode_before_syscall(tmp_path, monkeypatch):
    selected = tmp_path/'selected'; staged = tmp_path/'staged'
    selected.mkdir(); staged.mkdir()
    monkeypatch.setattr(completion, 'DEFINITION', selected)
    monkeypatch.setattr(completion, 'STAGING', staged)
    host = completion.ProductionCompletionHost(expected_sha='a'*40, manifest_sha256='b'*64,
        original_artifact_sha256={name:'c'*64 for name in completion.NAMES})
    monkeypatch.setattr(host, '_require_same_config_root', lambda:None)
    host._original_identity = ('foreign',)
    host._swap = lambda *_:pytest.fail('changed inode reached exchange')
    with pytest.raises(completion.EnrollmentCompletionError): host.exchange()


@pytest.fixture
def production(original, monkeypatch):
    """Actual production snapshot/completion; virtualize only installed OS reads.

    Canonical producer, reference retention, source validator, preimage checks,
    completion sequencing and post-swap readback remain their actual code.
    No installed path, UID, secret or service is accessed by these fixtures.
    """
    import dataclasses
    from control_plane import codex_provider_realm as realm, codex_worker
    from control_plane import executive_physical_resources as physical, model_router
    from ops.executive_os import subscription_provider_credential as credential
    from ops.executive_os import credential_rotation_interlock as interlock
    artifacts, inputs = copy.deepcopy(original)
    encode = lambda value:(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
    digest = lambda value:hashlib.sha256(value).hexdigest()
    manifest = encode({'commit_sha':'a'*40,'tree_sha':'b'*40})
    receipt = encode({'schema_version':'mastermind.attended_claude_binary/v1',
                      'binary':dataclasses.asdict(inputs['binary'])})
    row = dict(schema='mastermind.provider_native_capability_registration/v1',
        capacity_capability_id='fixture.minimax', capability_generation=1,
        provider='minimax',billing_mode='subscription',credential_kind='api_key',
        execution_surface='native_cli',registration_state='registered',material_source_digest='c'*64)
    row['registration_receipt_digest'] = digest(json.dumps(row,sort_keys=True,separators=(',',':')).encode())
    export = dict(repository_commit='a'*40,previous_repository_commit='b'*40,
                  material_source_digest='c'*64,registrations=[row])
    inputs.update(release_root=str(completion.SYSTEM/'releases'/('a'*40)),
        release_manifest_sha256=digest(manifest),python_binary=completion.PYTHON,
        binary_receipt_path=str(completion.SYSTEM/'config/claude-minimax-finite-01-attestation.json'),
        binary_receipt_sha256=digest(receipt),routing_root_id=completion.ROOT_ID,
        routing_parent_run_id=completion.ROOT_ID,model_class='routine')
    inputs['native_capacity_enrollment']['registration_source']['export_sha256'] = digest(encode(export))
    artifacts = build_finite_worker_artifacts(**inputs)
    host = completion.ProductionCompletionHost(expected_sha='a'*40,manifest_sha256=digest(manifest),
        original_artifact_sha256={k:digest(v) for k,v in artifacts.items()})
    def info(inode, uid=0, gid=0, mode=stat.S_IFDIR|0o755):
        return SimpleNamespace(st_dev=1,st_ino=inode,st_uid=uid,st_gid=gid,st_mode=mode,
            st_nlink=1,st_size=100,st_mtime_ns=10,st_ctime_ns=20)
    fs = SimpleNamespace(selected=artifacts,staged=None,selected_info=info(1),staged_info=info(2),
                         calls=[],active=set(),unsafe=None,metadata=info(3,470,470,stat.S_IFREG|0o600))
    control = {k:False for k in ('coo_autonomy_armed','coo_operator_harness_armed',
        'coo_foreground_only','ceo_submit_armed','fabric_bridge_armed')}
    prior = SimpleNamespace(control=control,worker=inputs['primary_config'],
        control_sha256='e'*64,worker_sha256=completion.PRIMARY_SHA256)
    prior.worker['operator_harness_armed']=False
    # Match actual canonical reconstruction after adding the explicit arm flag.
    inputs['primary_config']=prior.worker
    monkeypatch.setattr(host,'_require_same_config_root',lambda:None)
    monkeypatch.setattr(host.owner,'require_exact_install',lambda sha:sha)
    monkeypatch.setattr(host.owner,'require_transaction_absent',lambda:None)
    monkeypatch.setattr(host.owner,'load_unarmed_configs',lambda sha:prior)
    monkeypatch.setattr(host.owner,'_loaded_observe_only',lambda label:False)
    monkeypatch.setattr(host.owner,'_configs',lambda:(None,None,prior.control_sha256,prior.worker_sha256))
    monkeypatch.setattr(interlock,'assert_credential_mutation_disarmed',lambda:None)
    monkeypatch.setattr(physical,'load_physical_resource_policy',lambda:{
        'canonical_runtime':{'host_id':None},'qualification':'UNQUALIFIED','production_armed':False})
    monkeypatch.setattr(completion,'checked_command',lambda argv:SimpleNamespace(stdout=b'disabled services = {\n}\n'))
    monkeypatch.setattr(completion,'_absent',lambda path:None)
    monkeypatch.setattr(host,'_read_artifacts',lambda path:fs.selected if path==completion.DEFINITION else fs.staged)
    home = Path(json.loads(artifacts['worker.json'])['provider_home'])
    monkeypatch.setattr(completion.pwd,'getpwnam',lambda name:SimpleNamespace(
        pw_name=name,pw_uid=470,pw_gid=470,pw_dir=str(home),pw_shell='/usr/bin/false'))
    monkeypatch.setattr(completion.grp,'getgrnam',lambda name:SimpleNamespace(gr_name=name,gr_gid=470))
    monkeypatch.setattr(credential,'_assert_worker_quiescent',lambda uid:None)
    monkeypatch.setattr(credential,'verify_provider_credential',lambda config:home/'provider-credential')
    monkeypatch.setattr(credential,'_credential_metadata',lambda *a,**kw:fs.metadata)
    monkeypatch.setattr(completion,'protected_bytes',lambda path,**kw:
        manifest if path.name=='.executive-release-manifest.json' else receipt)
    monkeypatch.setattr(codex_worker,'_assert_binary_unchanged',lambda binary:
        fs.calls.append(('binary-check',frozenset(fs.active))))
    monkeypatch.setattr(model_router.ModelRouter,'load',lambda:SimpleNamespace(
        capability_registry=SimpleNamespace(resolve=lambda _:SimpleNamespace(profile_digest='e'*64))))
    def source_read(path, expected):
        assert expected == digest(encode(export))
        fs.calls.append(('source',frozenset(fs.active)))
        return copy.deepcopy(export)
    monkeypatch.setattr(realm,'_native_read_config',source_read)
    @contextmanager
    def native_open(path, **kw):
        label = 'home' if path==home else 'binary'
        assert (kw=={'directory':True,'private_uid':470}) if label=='home' else (kw=={} and str(path)=='/fixture/claude')
        fs.calls.append(('open',label))
        if fs.unsafe in (label+'-ancestor', label+'-acl'):
            raise realm.ProviderRealmError('fixture unsafe ancestor or ACL')
        fs.active.add(label)
        try:
            yield 100,info(4,470,470,stat.S_IFDIR|0o700) if label=='home' else info(5,mode=stat.S_IFREG|0o555)
            if fs.unsafe==label+'-replacement':
                raise realm.ProviderRealmError('fixture named leaf replaced')
        finally:
            fs.active.remove(label);fs.calls.append(('close',label))
    monkeypatch.setattr(realm,'_native_open',native_open)
    old_lstat = Path.lstat
    monkeypatch.setattr(Path,'lstat',lambda path:fs.selected_info if path==completion.DEFINITION
        else fs.staged_info if path==completion.STAGING else old_lstat(path))
    @contextmanager
    def interval():
        fs.calls.append(('lock',None));yield;fs.calls.append(('unlock',None))
    monkeypatch.setattr(host,'interval',interval)
    def absent():
        if fs.staged is not None:raise completion.EnrollmentCompletionError()
    monkeypatch.setattr(host,'require_staging_absent',absent)
    def stage(target):
        fs.calls.append(('stage',None));fs.staged=target
    monkeypatch.setattr(host,'stage',stage)
    def swap():
        fs.calls.append(('swap',None))
        fs.selected,fs.staged=fs.staged,fs.selected
        fs.selected_info,fs.staged_info=fs.staged_info,fs.selected_info
    monkeypatch.setattr(host,'exchange',swap)
    return SimpleNamespace(host=host,fs=fs,original=artifacts,export=export,prior=prior)


def test_actual_production_snapshot_complete_generation_and_postswap_readback(production):
    p=production
    result=completion.execute_completion(p.host)
    assert result['state']=='ENROLLED' and result['provider_auth']=='UNKNOWN'
    assert p.fs.staged==p.original
    assert json.loads(p.fs.selected['worker.json'])['native_capacity_enrollment']['enrollment_state']=='enrolled'
    assert [name for name,_ in p.fs.calls].count('stage')==1
    assert [name for name,_ in p.fs.calls].count('swap')==1
    assert all(value=={'home','binary'} for name,value in p.fs.calls if name=='source')
    assert all(value=={'home','binary'} for name,value in p.fs.calls if name=='binary-check')
    assert not p.fs.active


@pytest.mark.parametrize('unsafe',['home-ancestor','home-acl','home-replacement',
                                   'binary-ancestor','binary-acl','binary-replacement'])
def test_actual_production_custody_refuses_before_staging(production, unsafe):
    p=production;p.fs.unsafe=unsafe
    with pytest.raises(completion.EnrollmentCompletionError) as result:
        completion.execute_completion(p.host)
    assert result.value.effect_unknown is False
    assert p.fs.staged is None and p.fs.selected==p.original
    assert not {'stage','swap'}.intersection(name for name,_ in p.fs.calls)
    assert not p.fs.active
