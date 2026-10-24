"""Installed P is not accepted P: genuine sixteen-origin source, typed R successor.

Actual normal input producer and whole config encoding remain real. Existing
Root/account/ACL/release/install-plist/ancestor/assignment observations are
explicit inert host seams; actual migrations/helper/issuance/proof/restore and
summary/carry validators are never stubbed. No live host or provider effects.
"""
import copy
import fcntl
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest
from ops.executive_os import acceptance_maintenance as m
from ops.executive_os import prepare_control_successor as producer
from tests import test_executive_acceptance_v5_to_v7 as fixtures
from tests import test_executive_prepared_migration_successor as prepared
from tests.test_executive_spent_ctime_qualification import _no_external_effects
from tests.test_prepare_control_successor import control_input

P, R = prepared.P, prepared.R


def _rewrite(path, raw):
    path.chmod(0o600); path.write_bytes(raw); path.chmod(0o440)


def _installed_fixture(tmp_path, monkeypatch):
    real = fixtures._v5_host_fixture
    def full_config(*args, **kwargs):
        f = real(*args, **kwargs)
        complete = control_input.__wrapped__()
        complete.update(f.config)
        complete.update(control_uid=os.getuid(), worker_uid=os.getuid()+1,
                        worker_gid=os.getgid()+1, shared_run_gid=os.getgid()+1,
                        ceo_ingress_app_armed=False, terminal_return_armed=False,
                        terminal_return_socket_path='/var/run/mastermind-agent-relay/agent-relay.sock')
        f.config.clear(); f.config.update(complete)
        _rewrite(m.SYSTEM_ROOT/'config/control.json',
                 (json.dumps(f.config, sort_keys=True, indent=2)+'\n').encode())
        return f
    monkeypatch.setattr(fixtures, '_v5_host_fixture', full_config)
    f = prepared._completed_preparation(tmp_path, monkeypatch)
    f.install_checks = []
    # Existing host seal/plist observation input; no fake PASS or DB validator.
    monkeypatch.setattr(m, '_require_preparation_install', lambda sha: f.install_checks.append(sha))
    original = m.sealed_bytes(f.parent_bundle/'source-control.json', m._MAX_DOCUMENT_BYTES)
    supplied = producer.build_successor(producer._parse(original), source_sha=P,
        macro_root=producer._parse(original)['ceo_ingress_app_macro_root'])
    assert supplied['privileged_readiness_armed'] is True
    supplied['terminal_return_socket_path'] = '/var/db/mastermind-agent-relay/socket/agent-relay.sock'
    f.installed_raw = (json.dumps(supplied, sort_keys=True, indent=2, ensure_ascii=False)+'\n').encode()
    assert f.installed_raw == m._normal_installed_preparation_config(original, P)
    f.config.clear(); f.config.update(supplied)
    _rewrite(m.SYSTEM_ROOT/'config/control.json', f.installed_raw)
    f.old_args = copy.deepcopy(f.new_args)
    f.new_args.supersede_unstarted_migration_preparation_sha = None
    f.new_args.supersede_installed_unstarted_migration_preparation_sha = P
    f.new_args.expected_installed_parent_control_config_sha256 = hashlib.sha256(f.installed_raw).hexdigest()
    return f


def test_actual_normal_installed_P_to_R_prepare_admit_restore_finish_and_carry(tmp_path, monkeypatch):
    f = _installed_fixture(tmp_path, monkeypatch)
    with pytest.raises(m.MaintenanceError, match='config or original root'):
        m.prepare(f.old_args)
    result = m.prepare(f.new_args); descriptor = m.descriptor_for(R)
    assert descriptor['schema_version'] == m.SCHEMA_INSTALLED_PREPARED_MIGRATION_SUCCESSOR
    assert descriptor['installed_parent_control_config_sha256'] == hashlib.sha256(f.installed_raw).hexdigest()
    assert len(list(result.iterdir())) == 9
    assert (result/m._INSTALLED_PARENT_CONTROL_NAME).read_bytes() == f.installed_raw
    assert all((result/name).read_bytes() == (f.parent_bundle/name).read_bytes()
        for name in m._V5_TO_V7_BUNDLE_NAMES-{'descriptor.json','preparing.json'})
    prepared._assert_parent_unchanged(f)
    actual_r = m._normal_installed_preparation_config(f.installed_raw, R)
    f.config.clear(); f.config.update(json.loads(actual_r))
    _rewrite(m.SYSTEM_ROOT/'config/control.json', actual_r)
    owner = m.Maintenance(R, m.digest(descriptor), f.config)
    assert f.install_checks == [P, P, R, R]
    monkeypatch.setattr(fixtures, 'SUCCESSOR', R)
    proof_ids = fixtures._actual_proof_delta(f, descriptor)
    receipt, verification, drill, applied = fixtures._proof_backup_chain(f, tmp_path)
    acceptance = fixtures._write_proof_receipts(f, receipt, verification, drill, applied)
    summary = acceptance/'acceptance-summary.json'
    fixtures._write_receipt(summary, fixtures._real_pass_summary(f, proof_ids))
    fd = os.open(f.lock, os.O_RDWR); fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
    live = sqlite3.connect(f.database); live.execute('PRAGMA journal_mode=WAL')
    with live: live.execute('UPDATE workers SET last_seen_at_ms=last_seen_at_ms+1,updated_at_ms=updated_at_ms+1,version=version+1')
    try: owner.finish(proof_ids, summary)
    finally: live.close(); fcntl.flock(fd,fcntl.LOCK_UN); os.close(fd)
    carry = m.sealed_json(result/'carry-forward.json')
    assert carry['schema_version'] == m.SCHEMA_INSTALLED_PREPARED_MIGRATION_SUCCESSOR
    future = {key:value for key,value in descriptor.items() if key in m._DESCRIPTOR_V2_KEYS}
    future.update(schema_version=m.SCHEMA_V2, predecessor_sha=R, successor_sha='1'*40,
        prior_descriptor_sha256=m.digest(descriptor),prior_carry_sha256=m.digest(carry),
        prior_summary_sha256=hashlib.sha256(summary.read_bytes()).hexdigest())
    bundle=m.bundle_path('1'*40);bundle.mkdir();m.write_sealed(bundle/'descriptor.json',future,public=True)
    from control_plane.executive_runtime import Runtime
    Runtime.at(f.runtime_root).jobs.create_job('later unrelated installed-successor fixture job')
    m.validate_prior_carry_binding(future)
    prepared._assert_parent_unchanged(f)


@pytest.mark.parametrize('fault', ['config','privileged','macro','socket','arms','cas','install','database',
    'sequence','inventory','canary','parent-started','acceptance','mixed-selector'])
def test_installed_preparation_refuses_before_target_or_marker(tmp_path,monkeypatch,fault):
    f=_installed_fixture(tmp_path,monkeypatch)
    if fault in {'config','privileged','macro','socket','arms'}:
        value=dict(f.config)
        key,change={'config':('cost_class','foreign'), 'privileged':('privileged_readiness_armed',False),
                    'macro':('ceo_ingress_app_macro_root','/foreign/macro'),
                    'socket':('terminal_return_socket_path','/foreign/relay.sock'),
                    'arms':('coo_autonomy_armed',True)}[fault]
        value[key]=change;_rewrite(m.SYSTEM_ROOT/'config/control.json',(json.dumps(value,sort_keys=True,indent=2)+'\n').encode())
        f.new_args.expected_installed_parent_control_config_sha256=hashlib.sha256((m.SYSTEM_ROOT/'config/control.json').read_bytes()).hexdigest()
    elif fault=='cas': f.new_args.expected_installed_parent_control_config_sha256='0'*64
    elif fault=='install':
        def refuse(_): raise m.MaintenanceError('inert fullseal/plist refusal')
        monkeypatch.setattr(m,'_require_preparation_install',refuse)
    elif fault in {'database','sequence'}:
        with sqlite3.connect(f.database) as db:
            db.execute('UPDATE sqlite_sequence SET seq=seq+1')
    elif fault=='inventory': (Path(f.config['backup_root'])/'foreign').write_bytes(b'foreign')
    elif fault=='canary': Path(f.config['secret_canary_receipt_path']).write_text('{}')
    elif fault=='parent-started': m.write_sealed(f.parent_bundle/'run-started.json',{'schema_version':f.parent['schema_version']})
    elif fault=='acceptance': (f.runtime_root.parent/'acceptance'/P).mkdir()
    elif fault=='mixed-selector': f.new_args.supersede_unstarted_migration_preparation_sha=P
    with pytest.raises((m.MaintenanceError,ValueError, OSError)):
        m.prepare(f.new_args)
    assert not m.bundle_path(R).exists()


@pytest.mark.parametrize('fault',['config','install','installed-pin'])
def test_installed_preparation_final_publication_is_bound(tmp_path,monkeypatch,fault):
    f=_installed_fixture(tmp_path,monkeypatch)
    real=m._requalify_unstarted_preproof_v5_to_v7
    def late(*args,**kwargs):
        value=real(*args,**kwargs)
        if fault=='config': _rewrite(m.SYSTEM_ROOT/'config/control.json',f.installed_raw+b' ')
        elif fault=='install':
            def refuse(_): raise m.MaintenanceError('late actual install source changed')
            monkeypatch.setattr(m,'_require_preparation_install',refuse)
        else:
            directory=args[7];path=directory/m._INSTALLED_PARENT_CONTROL_NAME
            path.chmod(0o600);path.write_bytes(path.read_bytes()+b' ');path.chmod(0o400)
        return value
    monkeypatch.setattr(m,'_requalify_unstarted_preproof_v5_to_v7',late)
    with pytest.raises((m.MaintenanceError, ValueError,OSError)):m.prepare(f.new_args)
    assert not m.bundle_path(R).exists()


@pytest.mark.parametrize('fault',['config','install','installed-pin'])
def test_installed_preparation_admission_refuses_late_binding_before_marker(tmp_path,monkeypatch,fault):
    f=_installed_fixture(tmp_path,monkeypatch)
    result=m.prepare(f.new_args);descriptor=m.descriptor_for(R)
    raw=m._normal_installed_preparation_config(f.installed_raw,R)
    f.config.clear();f.config.update(json.loads(raw));_rewrite(m.SYSTEM_ROOT/'config/control.json',raw)
    real=m._requalify_unstarted_preproof_v5_to_v7
    def late(*args,**kwargs):
        value=real(*args,**kwargs)
        if fault=='config':_rewrite(m.SYSTEM_ROOT/'config/control.json',raw+b' ')
        elif fault=='install':
            def refuse(_):raise m.MaintenanceError('late install/plist refusal')
            monkeypatch.setattr(m,'_require_preparation_install',refuse)
        else:
            path=result/m._INSTALLED_PARENT_CONTROL_NAME
            path.chmod(0o600);path.write_bytes(path.read_bytes()+b' ');path.chmod(0o400)
        return value
    monkeypatch.setattr(m,'_requalify_unstarted_preproof_v5_to_v7',late)
    with pytest.raises((m.MaintenanceError,ValueError,OSError)):
        m.Maintenance(R,m.digest(descriptor),f.config)
    assert not (result/'run-started.json').exists()
    prepared._assert_parent_unchanged(f)


def test_final_install_observation_cannot_change_config_before_publication(tmp_path,monkeypatch):
    f=_installed_fixture(tmp_path,monkeypatch);calls=[]
    def install(sha):
        calls.append(sha)
        if len(calls)==2:_rewrite(m.SYSTEM_ROOT/'config/control.json',f.installed_raw+b' ')
    monkeypatch.setattr(m,'_require_preparation_install',install)
    with pytest.raises(m.MaintenanceError):m.prepare(f.new_args)
    assert calls==[P,P] and not m.bundle_path(R).exists()


@pytest.mark.parametrize('code',['platform_unsupported','installed_identity_mismatch','installed_identity_unavailable'])
def test_existing_exact_install_owner_refusal_is_not_bypassed(monkeypatch,code):
    from ops.executive_os import autonomy_control as ac
    calls=[]
    def refuse(self,sha):
        calls.append(sha);raise ac.HostControlError(code)
    # Keep the actual require_exact_install error mapping; only native host
    # observations are fixture inputs. The failed prior test used invalid Arm
    # error names and is retained as a fixture error, not a product failure.
    monkeypatch.setattr(ac.ProductionArmHost,'_require_host',lambda self:None)
    monkeypatch.setattr(ac.ProductionArmHost,'_release_identity',refuse)
    with pytest.raises(m.MaintenanceError,match='release or plist'):
        m._require_preparation_install(P)
    assert calls==[P]
