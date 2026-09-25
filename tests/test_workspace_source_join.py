"""Actual SQLite owner reads through source join; no company/source discovery."""
from contextlib import contextmanager
from types import SimpleNamespace
import dataclasses
import json
from pathlib import Path
import pytest
from control_plane import executive_runtime as er, workspace_source_join as join
from control_plane import chairman_control_room as ccr
from control_plane.ceo_intent import submit_intent
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_executive_runtime_bounded_read import ObservationNamespace
from tests.test_workspace_programs_qualification import empty_inputs
from tests.test_workspace_read_service import STAMP, cache_fixture, frame, run
from scripts import chairman_control_room as publisher


def intent(index=1, workstream='WS:ONE'):
    return {'schema':'mastermind.ceo_intent.v2','intent_id':f'JOIN-ROOT-{index:03}',
        'actor':'ceo-sol','objective':'Read bounded fixture root','department':'executive-infrastructure',
        'priority':5,'intent_kind':'executive_coo_cycle','business_impact':'material',
        'workstream':workstream,'grounding':{'mastermind_sha':'1'*40,'macro_sha':'2'*40,
            'boot_packet_schema':'mastermind.ceo_boot_packet.v1'},
        'execution_contract':{'requested_authorities':['READ'],'attempt_limit':2}}


@pytest.fixture
def actual(tmp_path):
    root=tmp_path/'runtime';writer=er.Runtime.at(root)
    job=submit_intent(writer,intent())['job_id']
    keeper=er.sqlite3.connect(writer.store.path,isolation_level=None);keeper.execute('SELECT 1 FROM jobs').fetchone()
    namespace=ObservationNamespace(writer.store.path)
    def bound():return er.Runtime.at(root,create=False,read_binding=er.RuntimeReadBinding(namespace))
    try:yield writer,bound,namespace,job
    finally:keeper.close()


def compose(tmp_path, actual, monkeypatch):
    writer,bound,namespace,job=actual
    args=empty_inputs();args['agent_os_state']['workstreams']=[{'key':'ONE','title':'One','owner':'ceo-sol','status':'active'}]
    macro=tmp_path/'macro';macro.mkdir()
    for name,rel in [('active_builds',ccr.ACTIVE_BUILDS_RELATIVE_PATH),('agent_os_state',ccr.AGENT_OS_STATE_RELATIVE_PATH)]:
        f=macro/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(args[name]))
    calls=[]
    def packet(**kwargs):calls.append(kwargs);return args['boot_packet']
    build=join.build_workspace_composer(packet_collector=packet,repo_root=tmp_path/'source',macro_root=macro,bounded_runtime=bound,bindings_path=None)
    assert calls==[] and namespace.entries==0
    doc=build(STAMP)
    assert calls[0]['now']==STAMP and calls[0]['macro_root_flag']==str(macro)
    return doc


def test_actual_sqlite_to_canonical_program_and_partial_mission(tmp_path,actual,monkeypatch):
    writer,bound,namespace,job=actual
    traces=[];old=er.sqlite3.connect
    def connection(*a,**k):
        c=old(*a,**k);c.set_trace_callback(traces.append);return c
    monkeypatch.setattr(er.sqlite3,'connect',connection)
    monkeypatch.setattr(er.JobRegistry,'list_jobs',lambda *a,**k:pytest.fail('unbounded jobs'))
    monkeypatch.setattr(er.AttemptRegistry,'list_attempts',lambda *a,**k:pytest.fail('unbounded attempts'))
    doc=compose(tmp_path,actual,monkeypatch)
    card=doc['autonomy']['responsibilities'][0]
    assert card['root_job_id']==job and card['dispatch']['dispatch_state']=='UNKNOWN'
    assert card['is_actionable'] is False
    assert namespace.entries==namespace.exits and not namespace.active
    assert sum('FROM events' in s and 'command_id=' in s for s in traces)>=2
    owners,clock,cache=cache_fixture(tmp_path/'cache');owner=owners[0]
    owner.state_cache['doc']=doc;owner.state_cache.pop('source_validity_bounds',None)
    with owner.state_lock:publisher._publish_source_validity(owner,doc,tuple(clock),tuple(clock))
    service=WorkspaceReadService(cache=cache,runtime=writer,authorize=lambda p:True,armed={},runtime_identity={'db_present':True},bounded_runtime=lambda r:bound())
    programs=run(service,frame('programs'))['result'];assert programs['availability']=='AVAILABLE'
    selected=frame();selected['selection']['root_job_id']=job
    mission=run(service,selected)
    assert mission['ok'] is True,mission
    assert mission['result']['read_state']['state']=='PARTIAL'
    assert mission['result']['source']['owner_observation']['runtime']['state']=='SAME'


def test_unsupported_root_never_becomes_complete_empty_mapping(actual):
    writer,bound,namespace,job=actual
    writer.jobs.create_job('unsupported fixture root')
    inputs=join._bounded_runtime_inputs(bound())
    assert inputs[0] is None and inputs[1] is None and inputs[4]
    assert namespace.entries==namespace.exits


def test_duplicate_workstream_roots_are_not_collapsed(actual):
    writer,bound,namespace,job=actual
    second=submit_intent(writer,intent(2))['job_id']
    inputs=join._bounded_runtime_inputs(bound())
    assert {row['job_id'] for row in inputs[0]}=={job,second}


def test_point_budget_refuses_before_any_event(actual,monkeypatch):
    writer,bound,namespace,job=actual
    for index in range(2,19):submit_intent(writer,intent(index))
    monkeypatch.setattr(er.BoundedRuntimeReadObservation,'get_creation_event_by_command_id',lambda *a,**k:pytest.fail('overbudget Event'))
    inputs=join._bounded_runtime_inputs(bound())
    assert inputs[0] is None and inputs[4]


def test_bounded_reader_signature_does_not_fall_back():
    calls=[]
    with pytest.raises(TypeError):join._read_installed_document(lambda root:calls.append(root),'fixture')
    assert calls==[]


@pytest.mark.parametrize('fault', ['discovery_truncated', 'detail_failure', 'receipt_refusal', 'changed_root'])
def test_observation_failure_never_retains_a_partial_mapping(actual, monkeypatch, fault):
    writer, bound, namespace, job_id = actual
    if fault == 'discovery_truncated':
        original = er.BoundedRuntimeReadObservation.discover_job_roots_bounded
        def discover(read):
            return dataclasses.replace(original(read), truncated=True)
        monkeypatch.setattr(er.BoundedRuntimeReadObservation, 'discover_job_roots_bounded', discover)
    elif fault == 'detail_failure':
        def fail(read, root):
            raise ValueError('fixture detail failure')
        monkeypatch.setattr(er.BoundedRuntimeReadObservation, 'read_job_root_bounded', fail)
    elif fault == 'receipt_refusal':
        original = join._same_receipt
        checks = []
        def receipt(value):
            checks.append(value)
            return original(value) and len(checks) == 1
        monkeypatch.setattr(join, '_same_receipt', receipt)
    else:
        original = join._root_evidence
        def changed(runtime, root):
            jobs, attempts, provenance, receipt = original(runtime, root)
            provenance = dict(provenance)
            provenance[root] = dict(provenance[root], workstream='WS:CHANGED')
            return jobs, attempts, provenance, receipt
        monkeypatch.setattr(join, '_root_evidence', changed)
    result = join._bounded_runtime_inputs(bound())
    assert result[:3] == (None, None, None) and result[4]
    assert namespace.entries == namespace.exits and not namespace.active


def test_configured_publisher_uses_exact_composer_without_legacy_gather(tmp_path, monkeypatch):
    calls = []
    doc = {'schema': ccr.SCHEMA, 'generated_at': STAMP}
    def source(now):
        calls.append(now)
        return doc
    config = publisher.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
        token='fixture', origin='http://127.0.0.1:0', port=0, now_fn=lambda: STAMP,
        compose_inputs=source)
    monkeypatch.setattr(ccr, 'build_control_room', lambda **kw: pytest.fail('legacy source gather'))
    assert calls == []
    assert publisher._compose_state_doc(config) is doc and calls == [STAMP]


@pytest.mark.parametrize('fault', ['raises', 'malformed'])
def test_configured_publisher_failure_never_falls_back(tmp_path, monkeypatch, fault):
    def source(now):
        if fault == 'raises':
            raise RuntimeError('fixture unavailable collector')
        return {}
    config = publisher.ServerConfig(repo_root=tmp_path, macro_root=None, bindings_path=None,
        token='fixture', origin='http://127.0.0.1:0', port=0, compose_inputs=source)
    monkeypatch.setattr(ccr, 'build_control_room', lambda **kw: pytest.fail('legacy source gather'))
    with pytest.raises((RuntimeError, ValueError)):
        publisher._compose_state_doc(config)


@pytest.mark.parametrize('with_boot', [True, False])
def test_installed_factory_is_inert_and_uses_late_service_custody(tmp_path, monkeypatch, with_boot):
    from scripts import executive_os_phase1c as cli
    from tests.test_c1_ceo_ingress_composition import _raw
    from tests.test_workspace_read_app import _workspace_policy
    from integrations.executive_mcp.installed import InstalledBootPacketCollector
    from control_plane import executive_worker_broker
    raw = _raw(tmp_path)
    authority = {'schema': 'mastermind.workspace_acquisition_bindings.v1', 'profiles': {
        key: {'enabled': False, 'binding': None} for key in ('web', 'mac')}}
    raw.update(ceo_ingress_app_peer_uid=458, ceo_ingress_app_armed=False,
        ceo_ingress_app_macro_root=tmp_path/'macro', workspace_control_room={'port':8787},
        workspace_acquisition={}, workspace_resource_policy=json.loads(json.dumps(dataclasses.asdict(_workspace_policy()))))
    if with_boot:
        raw['ceo_ingress_app_boot_python'] = tmp_path/'sealed-python'
    monkeypatch.setattr(cli, '_attest_app_boot_runtime', lambda p: p)
    monkeypatch.setattr(cli, 'activate_launchd_socket', lambda name: object())
    monkeypatch.setattr(executive_worker_broker, 'WorkerBrokerClient', lambda *a, **k: object())
    captured = {}
    def composer(**kwargs):
        captured.update(kwargs)
        return lambda stamp: {'schema':ccr.SCHEMA,'generated_at':stamp}
    monkeypatch.setattr(join, 'build_workspace_composer', composer)
    class Service:
        def __init__(self, config, **kwargs):
            self.kwargs = kwargs
    monkeypatch.setattr(cli, 'ExecutiveControlService', Service)
    bindings = tmp_path/'existing-gui-bindings.json'
    if not with_boot:
        with pytest.raises(cli.ServiceError, match='sealed boot interpreter'):
            cli._service_from_config(raw, workspace_acquisition_loader=lambda: authority, workspace_bindings_path=bindings)
        assert captured == {}
        return
    service = cli._service_from_config(raw, workspace_acquisition_loader=lambda: authority, workspace_bindings_path=bindings)
    assert isinstance(captured['packet_collector'], InstalledBootPacketCollector)
    assert captured['repo_root'] == raw['proof_source_repository']
    assert captured['bindings_path'] == bindings
    # The canonical service is constructed after the inert callback. Only a
    # later refresh can ask that service's current custody for the actual owner.
    actual_runtime, facade = object(), object()
    calls = []
    service._require_runtime = lambda: actual_runtime
    service._namespace_custody = SimpleNamespace(bound_runtime=lambda actual: calls.append(actual) or facade)
    assert calls == []
    assert captured['bounded_runtime']() is facade and calls == [actual_runtime]
