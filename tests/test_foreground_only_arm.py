"""Foreground-only arm uses the existing transaction and digest-bound receipt."""
import dataclasses
import pytest
from ops.executive_os import autonomy_control as control
from scripts import executive_os_phase1c as cli
from tests.test_executive_autonomy_control import FakeTransactionHost, _arm_request, NOW
from tests.test_ceo_submit_armed_composition import _raw, _write
from tests.test_executive_fabric_phase1c import compose


def test_arm_persists_foreground_mode_and_disarm_clears_it():
    host = FakeTransactionHost()
    request = _arm_request(foreground_only=True)
    result = control.execute_arm(host, request, now=NOW)
    assert result.state == 'ARMED'
    assert host.control_config['coo_foreground_only'] is True
    assert host.receipt['control_config_sha256'] == control.sha256_bytes(control.encode_config(host.control_config))
    assert host.transaction_calls == list(FakeTransactionHost.PHASES)
    configs = control.ConfigEvidence(control_sha256='a'*64, worker_sha256='b'*64,
        control=host.control_config, worker=host.worker_config)
    off = control.derive_candidate_configs(configs, armed=False)
    assert off.control['coo_foreground_only'] is False
    assert off.control['coo_autonomy_armed'] is False
    assert off.worker['operator_harness_armed'] is False


@pytest.mark.parametrize('foreground,native', [(1,False),('true',False),(True,True)])
def test_invalid_mode_refuses_before_existing_arm_or_any_host_effect(foreground,native):
    host = FakeTransactionHost()
    host.existing_arm = lambda *a,**kw: pytest.fail('invalid mode reached host')
    with pytest.raises(control.ArmAdmissionError):
        control.execute_arm(host,_arm_request(foreground_only=foreground,native_return=native),now=NOW)
    assert host.transaction_calls == []


def test_loaded_config_propagates_mode_into_actual_service_config(tmp_path, monkeypatch):
    raw = _raw(tmp_path)
    raw.update(coo_foreground_only=True,coo_autonomy_armed=True)
    loaded=cli.load_control_config(_write(tmp_path,raw))
    service,_,_=compose(tmp_path,monkeypatch,loaded)
    assert service.config.coo_foreground_only is True


@pytest.mark.parametrize('changes', [dict(coo_foreground_only=1),
    dict(coo_foreground_only=True,coo_autonomy_armed=False),
    dict(coo_foreground_only=True,coo_autonomy_armed=True,coo_operator_model_alias='coo.operator.native-return')])
def test_bad_config_refuses_before_service_or_clients(tmp_path,changes):
    with pytest.raises(cli.ServiceError):
        cli.load_control_config(_write(tmp_path,_raw(tmp_path,**changes)))


@pytest.mark.parametrize('selected,requested',[(False,False),(False,True),(True,False),(True,True)])
def test_production_arm_replay_cannot_change_foreground_mode(selected,requested,monkeypatch):
    from tests.test_executive_autonomy_control import _snapshot, SHA
    fake=FakeTransactionHost()
    control.execute_arm(fake,_arm_request(foreground_only=selected),now=NOW)
    c,w=fake.control_config,fake.worker_config
    cd,wd=fake.receipt['control_config_sha256'],fake.receipt['worker_config_sha256']
    snapshot=_snapshot(control_config_sha256=cd,worker_config_sha256=wd,
        evidence={'control_armed':True,'worker_armed':True})
    host=control.ProductionTransactionHost()
    host.require_exact_install=lambda _:SHA
    host.collect_status=lambda *a,**kw:snapshot
    host.validate_gate_b=lambda *a:'4'*64
    host.validate_acceptance=lambda *a:'3'*64
    host._configs=lambda:(c,w,cd,wd,control.encode_config(c),control.encode_config(w))
    monkeypatch.setattr(control,'status_document',lambda *a,**kw:{'status':'ARMED_READY'})
    monkeypatch.setattr(control,'_root_json',lambda *a,**kw:(fake.receipt,b'receipt'))
    if selected==requested:
        assert host.existing_arm(_arm_request(foreground_only=requested),now=NOW).replayed
    else:
        with pytest.raises(control.ArmAdmissionError,match='changed_arm_evidence'):
            host.existing_arm(_arm_request(foreground_only=requested),now=NOW)


def test_foreground_mode_reaches_operator_recovery_owner(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from control_plane import executive_worker_broker as broker
    from control_plane.executive_runtime import Runtime
    raw=_raw(tmp_path,coo_foreground_only=True,coo_autonomy_armed=True)
    raw=cli.load_control_config(_write(tmp_path,raw))
    captured={}
    def service(config,**owners):captured.update(owners);return SimpleNamespace(config=config)
    monkeypatch.setattr(cli,'ExecutiveControlService',service)
    monkeypatch.setattr(cli,'activate_launchd_socket',lambda *a:object())
    monkeypatch.setattr(broker,'WorkerBrokerClient',lambda *a,**kw:object())
    cli._service_from_config(raw)
    runtime=Runtime.at(tmp_path/'factory-runtime')
    operator=captured['operator_supervisor_factory'](runtime,SimpleNamespace())
    assert operator.foreground_only is True
