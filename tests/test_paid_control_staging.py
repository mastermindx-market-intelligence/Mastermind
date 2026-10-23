"""Existing global transaction with temporary inert Root-custody fixtures only."""
import json
from types import SimpleNamespace
from datetime import datetime,timezone
import pytest
from ops.executive_os import autonomy_control as owner
from ops.executive_os import paid_control_staging as staging
from tests.test_executive_autonomy_control import SHA,_inprocess_marker_host


def replace_fixture(path,raw):
    temp=path.with_suffix('.fixture');temp.write_bytes(raw);temp.chmod(0o440);temp.replace(path)


@pytest.fixture
def installed(monkeypatch,tmp_path):
    _inprocess_marker_host(monkeypatch,tmp_path)
    value=json.loads(owner.CONTROL_CONFIG.read_bytes())
    value.update(coo_autonomy_armed=False,coo_operator_harness_armed=False,
        coo_foreground_only=False,ceo_submit_armed=False)
    replace_fixture(owner.CONTROL_CONFIG,owner.encode_config(value))
    worker=json.loads(owner.WORKER_CONFIG.read_bytes());worker['operator_harness_armed']=False
    replace_fixture(owner.WORKER_CONFIG,owner.encode_config(worker))
    host=staging.ProductionPaidStagingHost();host._paid_definition_sha256='d'*64
    for name,func in {'effective_uid':lambda:0,'require_exact_install':lambda sha:sha,
        'require_services_already_stopped':lambda:None,'require_service_uids_quiescent':lambda:None,
        'require_runtime_quiescent':lambda config:None}.items():monkeypatch.setattr(host,name,func)
    delta={'canonical_paid_fabric':{'bindings_path':str(staging.DEFINITION/'bindings.json'),
        'bindings_sha256':'a'*64}}
    monkeypatch.setattr(host,'read_delta',lambda:json.loads(json.dumps(delta)))
    def validate(tx):
        path,_=host._candidate_paths(tx.transaction_id);raw=path.read_bytes()
        return json.loads(raw),raw,owner.WORKER_CONFIG.read_bytes()
    monkeypatch.setattr(host,'_read_validated_control_candidate',validate)
    s=SimpleNamespace(host=host,delta=delta,control=owner.CONTROL_CONFIG.read_bytes(),worker=owner.WORKER_CONFIG.read_bytes())
    yield s
    if host._transaction_owner_fd is not None:host._release_transaction_owner()


def stage(s):return staging.execute_staging(s.host,SHA,owner.sha256_bytes(s.control))


def test_global_owner_publishes_only_paid_reference_and_keeps_worker_unchanged(installed):
    s=installed;tx=stage(s)
    assert tx.startswith('autonomy-')
    target=json.loads(owner.CONTROL_CONFIG.read_bytes());prior=json.loads(s.control)
    assert target==dict(prior,**s.delta)
    assert owner.WORKER_CONFIG.read_bytes()==s.worker
    assert not owner.AUTONOMY_TRANSACTION.exists()


def test_existing_disarm_receipt_keeps_authority_and_times(installed):
    s=installed;prior=s.host.checked_configs(SHA)
    candidate=owner.CandidateConfigs(prior.control,prior.worker,prior.control_bytes,prior.worker_bytes,
        prior.control_sha256,prior.worker_sha256)
    tx=owner.TransactionContext('autonomy-'+'1'*12,SHA,prior,candidate,None)
    old=owner.build_transaction_receipt(tx,state='DISARMED',now=datetime.now(timezone.utc))
    owner.AUTONOMY_RECEIPT.write_bytes(owner._encoded_json(old));owner.AUTONOMY_RECEIPT.chmod(0o444)
    transaction=stage(s);new=json.loads(owner.AUTONOMY_RECEIPT.read_bytes())
    assert new['transaction_id']==transaction
    ignored={'control_config_sha256','prior_control_config_sha256','transaction_id'}
    assert {k:v for k,v in old.items() if k not in ignored}=={k:v for k,v in new.items() if k not in ignored}


@pytest.mark.parametrize('key',['ceo_submit_armed','coo_autonomy_armed','coo_operator_harness_armed','coo_foreground_only','fabric_bridge_armed'])
def test_armed_control_refuses_before_global_marker(installed,key):
    s=installed;value=json.loads(s.control);value[key]=True
    replace_fixture(owner.CONTROL_CONFIG,owner.encode_config(value))
    with pytest.raises(Exception):staging.execute_staging(s.host,SHA,owner.sha256_bytes(owner.CONTROL_CONFIG.read_bytes()))
    assert not owner.AUTONOMY_TRANSACTION.exists()


@pytest.mark.parametrize('key',['fabric_attended_probe','native_capacity_v2','fabric_bindings_path'])
def test_finite_mixed_selection_refuses(installed,key):
    s=installed;value=json.loads(s.control);value[key]={}
    replace_fixture(owner.CONTROL_CONFIG,owner.encode_config(value))
    with pytest.raises(Exception):staging.execute_staging(s.host,SHA,owner.sha256_bytes(owner.CONTROL_CONFIG.read_bytes()))
    assert not owner.AUTONOMY_TRANSACTION.exists()


def test_crash_after_control_publication_is_same_transaction_readback_only(installed,monkeypatch):
    s=installed
    def lost(tx):raise RuntimeError('inert loss after actual temporary config publication')
    monkeypatch.setattr(s.host,'publish_disarmed_receipt',lost)
    with pytest.raises(owner.TransactionEffectUnknown):stage(s)
    original=owner.CONTROL_CONFIG.read_bytes()
    manifest=s.host._manifest();assert manifest['operation']=='PAID_CONTROL_STAGE'
    assert manifest['paid_definition_sha256']=='d'*64
    monkeypatch.setattr(s.host,'replace_control_config',lambda *a:pytest.fail('replay'))
    # No disarm receipt existed; exact absent pre/target is a valid postimage.
    s.host._release_transaction_owner()
    assert s.host.reconcile_staging(SHA)==manifest['transaction_id']
    assert owner.CONTROL_CONFIG.read_bytes()==original


def test_partial_receipt_refuses_reconciliation_without_repair(installed,monkeypatch):
    s=installed
    monkeypatch.setattr(s.host,'replace_control_config',lambda *a:(_ for _ in ()).throw(RuntimeError('before write')))
    with pytest.raises(owner.TransactionEffectUnknown):stage(s)
    s.host._release_transaction_owner()
    with pytest.raises(owner.TransactionEffectUnknown):s.host.reconcile_staging(SHA)
    assert owner.CONTROL_CONFIG.read_bytes()==s.control
    assert owner.AUTONOMY_TRANSACTION.exists()
