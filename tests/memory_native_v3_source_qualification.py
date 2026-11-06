"""Explicit one-run cross-repo source qualification, not default CI collection.

Invoke this exact file with MM_MEMORY_V3_MACRO_ROOT naming the verified 9fb08
source kit and MM_MEMORY_V3_JOIN_RETURN naming a fresh evidence destination.
Real temporary Runtime/Broker/receipts and Macro production exchange execute.
OS/install/key/current grants, economic clock and model process are the original
explicit inert fixtures. No real SSH, credential, provider or study is invoked.
"""
import asyncio
import copy
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest
from common import memory_native_wire as wire
from common.memory_participant_view import selected_descriptors
from control_plane import native_memory_admission as admission
from control_plane import memory_native_issuer as facade
from control_plane import protected_memory_peer as peer
from control_plane import protected_memory_profile as profile
from control_plane import executive_memory_issuer as root
from tests.test_protected_memory_execution import joined
from tests.test_protected_memory_profile import configured
from tests.test_protected_memory_peer import installed
from tests.test_protected_memory_economic import economy
from tests.test_memory_v3_completed_service_read import install_fixture_service_policy

REAL_POPEN=subprocess.Popen
REAL_UID=os.geteuid
SOURCE_MODULE_SHA='b0070ee025345cfaf97c11102e55345bd9661a3127f9f3deebfce7f50827ef86'

def test_actual_macro_exchange_to_genuine_m2_original_execution_and_completed_reader(joined,tmp_path,monkeypatch):
    source=Path(os.environ['MM_MEMORY_V3_MACRO_ROOT']).resolve()
    destination=Path(os.environ['MM_MEMORY_V3_JOIN_RETURN']).resolve()
    assert not destination.exists() and destination.parent.is_dir()
    manifest_raw=(Path(__file__).parent/'fixtures/memory_native_v3_9fb08/SOURCE_MANIFEST.json').read_bytes()
    assert hashlib.sha256(manifest_raw).hexdigest()=='23dc4b963ffb160789de767db419dd454824007cb5be7f559752da22dc0f7dc4'
    source_manifest=json.loads(manifest_raw)
    assert source_manifest['source_head']=='9fb08c079c0048f3f9fe9549208b2afc1316119b'
    for relative,entry in source_manifest['paths'].items():
        path=source/relative
        assert path.is_file() and not path.is_symlink()
        body=path.read_bytes()
        assert len(body)==entry['bytes'] and hashlib.sha256(body).hexdigest()==entry['sha256']
    assert hashlib.sha256((source/'engine/research_factory/market_memory_e0_native_issuer.py').read_bytes()).hexdigest()==SOURCE_MODULE_SHA
    dependencies=json.loads((Path(__file__).parent/'fixtures/memory_native_v3_9fb08/FIXTURE_DEPENDENCIES.json').read_text())
    for dependency in dependencies['entries']:
        assert hashlib.sha256((source/dependency['source_path']).read_bytes()).hexdigest()==dependency['sha256']
    import tests
    monkeypatch.setattr(tests,'__path__',[*tests.__path__,str(source/'tests')])
    monkeypatch.syspath_prepend(str(source))
    # Materialize the actual archived empty package initializer: a namespace
    # path patch alone has no __file__ for native source qualification. Keep
    # Mastermind's unrelated engine.canon fixture module byte-for-byte intact.
    spec=importlib.util.spec_from_file_location('engine',source/'engine/__init__.py',
        submodule_search_locations=[str(source/'engine')])
    engine=importlib.util.module_from_spec(spec)
    if 'engine.canon' in sys.modules:engine.canon=sys.modules['engine.canon']
    monkeypatch.setitem(sys.modules,'engine',engine);spec.loader.exec_module(engine)
    native=importlib.import_module('tests.test_market_memory_e0_native_issuer')
    native_case=importlib.import_module('tests.test_market_memory_e0_native_case')
    primitives=importlib.import_module('tests.market_memory_native_peer_fixtures')
    issuer=native.issuer;case=native.case
    assert Path(issuer.__file__).resolve()==source/'engine/research_factory/market_memory_e0_native_issuer.py'
    original_source_before=native_case.source_guard_snapshot()
    runtime,job,lease,_,processes,_,errors,state,run=joined
    trace=[];summary={'schema':'mastermind.memory_actual_v3_source_join.v1','complete':False,
        'consumer_base':'c2b0614381959ab3092ea2407c851144511b65dc',
        'producer_source':'9fb08c079c0048f3f9fe9549208b2afc1316119b',
        'fixture_authority':'M2 installed/kernel/root/config and Linux OS/key/admin grant primitives substituted; actual temporary owner/data/receipt code runs',
        'economic_clock':'original accepted inert clock, not live budget/deadline proof',
        'provider':'inert existing model child fixture, not provider execution',
        'additional_same_commit_public_fixture_dependencies':dependencies,
        'ssh':False,'scientific_admission':False,'retry_authorized':False,'verification':dict(wire.FLAGS),
        'trace':trace}
    def checkpoint():
        temporary=destination.with_suffix('.partial.json')
        temporary.write_text(json.dumps(summary,indent=2)+'\n')
        os.replace(temporary,destination)
    with monkeypatch.context() as linux:
        low=primitives.native_peer_primitives.__wrapped__(linux)
        native_cap=primitives.native_peer_capability.__wrapped__(low)
        # Explicit M2 transport installation fixture uses the actual native
        # primitive fixture's key identity BEFORE deriving the original input.
        config=json.loads(state['config']['raw'])
        config['memory_native_issuer']['service_key_fingerprint']=low['fingerprint']
        state['config']['raw']=profile.canonical(config)
        state['config']['owner']['configuration_sha256']=hashlib.sha256(state['config']['raw']).hexdigest()
        linux.setattr(root,'_enrollment',lambda _:(state['config']['raw'],low['fingerprint'],b'inert-known',('inert-key-metadata',)))
        current_owner=facade.describe_control_owner()
        claim=admission.capture_memory_runtime_claim(runtime,lease)
        original=peer.capture_control_memory_intent(claim,current_owner)
        projection,qualified_request=facade._request(original,'qualify_current_case',version='v3')
        actual_intent=qualified_request['intent'];operation=qualified_request['operation_id']
        assert actual_intent['participant_binding_sha256']==hashlib.sha256(peer.canonical(projection)).hexdigest()
        assert actual_intent['participant_binding_sha256']!='a'*64
        summary.update(operation_id=operation,attempt_id=lease.attempt.attempt_id,
            pre_input_sha256=actual_intent['participant_binding_sha256'])
        # New fixture admin setup is derived from that REAL original. No old
        # vector, original runtime row, input or production source is rewritten.
        linux.setattr(native_case,'INTENT',copy.deepcopy(actual_intent))
        records=native.records.__wrapped__()
        for value in records.values():value['study_id']=actual_intent['study_id']
        linux.setattr(case,'_SOURCE_PATHS',issuer.FULL_SOURCE_PATHS)
        source_before=native_case.source_guard_snapshot()
        linux.setattr(issuer,'_platform',lambda:'linux');linux.setattr(issuer,'_uid',lambda:0)
        temporary=tmp_path/'linux';temporary.mkdir()
        with native_case.isolated_install(temporary,linux) as installed_root:
            linux.setattr(issuer,'ROOT',installed_root)
            def git_only(argv,**kwargs):
                assert argv[:3]==['/usr/bin/git','-C',str(installed_root)]
                assert argv[3] in ('rev-parse','cat-file','ls-tree')
                return REAL_POPEN(argv,**kwargs)
            def in_linux(call):
                # Only original native fixture OS ownership is substituted;
                # source Git is genuine and strictly read-only/literal.
                with monkeypatch.context() as local:
                    local.setattr(os,'geteuid',REAL_UID)
                    local.setattr(subprocess,'Popen',git_only)
                    return call()
            generator=native_case._native_world(temporary,linux,records,native_cap,installed_root)
            world=in_linux(lambda:next(generator))
            try:
                recipient=copy.deepcopy(world['recipient']);recipient['operation_id']=operation
                world['recipient']=recipient
                world['records']['access']['scope_ref']=native_case.retain(world['directory'],recipient)
                world['selected']['control_refs']['access']=native_case.retain(world['directory'],world['records']['access'],'access_state_id')
                native_case.write(world['directory']/'SELECTED.json',native_case.canonical(world['selected']))
                summary['macro_fixture']=world['fixture_record']
                def exchange(frame):
                    req=wire.decode_request(frame)
                    assert req['operation_id']==operation and req['intent']==actual_intent
                    start=time.monotonic();cpu=time.process_time();output=io.BytesIO()
                    in_linux(lambda:issuer.serve(io.BytesIO(frame),output))
                    elapsed=time.monotonic()-start
                    response=wire.decode_response(output.getvalue(),request=req)
                    trace.append({'action':req['action'],'status':response['status'],
                        'wall_seconds':elapsed,'cpu_seconds':time.process_time()-cpu,
                        'request_sha256':hashlib.sha256(frame).hexdigest(),
                        'response_sha256':hashlib.sha256(output.getvalue()).hexdigest()})
                    checkpoint()
                    if elapsed>120:raise root.IssuerExchangeUnknown()
                    if 'input' in response:state['native_packet']=wire.packet(response['input'],response['locator'])
                    return output.getvalue()
                linux.setattr(root,'_exchange',exchange)
                checkpoint()
                # Existing attended Supervisor renews only the same actual
                # Runtime lease; no timer or paid allowance is increased.
                view=asyncio.run(state['supervisor'].run_protected_memory_case(lease))
                assert view['answer']=='Fixture untrusted answer' and view['verification']==wire.FLAGS
                assert not errors and len(processes)==1
                assert runtime.jobs.get_job(job.job_id).status.value=='COMPLETED'
                assert runtime.attempts.get_attempt(lease.attempt.attempt_id).status.value=='COMPLETED'
                assert (run/'memory-original-input').read_bytes()==state['native_packet']
                assert len(selected_descriptors(state['native_packet']))==10
                assert sum(x['action']=='prepare_case' for x in trace)==1
                assert in_linux(lambda:world['store'].snapshot())['consumed_looks']==1
                install_fixture_service_policy(joined)
                def assert_completed_read():
                    before=len(runtime.events.list_events());count=len(processes)
                    restored=state['supervisor'].read_completed_protected_memory_result(lease.attempt.attempt_id)
                    assert restored==view and len(runtime.events.list_events())==before and len(processes)==count
                assert_completed_read()
                access=copy.deepcopy(world['records']['access'])
                access.update(sequence=1,previous_state_ref=world['selected']['control_refs']['access'],
                    recorded_at='2026-10-14T00:05:00.000000Z',budget={'maximum_looks':3,'consumed_looks':1,'reserved_looks':0})
                world['selected']['control_refs']['access']=native_case.retain(world['directory'],access,'access_state_id')
                native_case.write(world['directory']/'SELECTED.json',native_case.canonical(world['selected']))
                assert_completed_read()
                # Genuine new store corruption is contained before any return;
                # no new prepare/load/refund/provider process can repair it.
                path=world['store'].directory/world['store']._result_name(operation)
                original_bytes=path.read_bytes()
                native_case.write(path,original_bytes[:-1]+bytes([original_bytes[-1]^1]))
                try:
                    with pytest.raises(ValueError):state['supervisor'].read_completed_protected_memory_result(lease.attempt.attempt_id)
                finally:native_case.write(path,original_bytes)
                assert sum(x['action']=='prepare_case' for x in trace)==1 and len(processes)==1
                assert 'Fixture untrusted answer' not in json.dumps(runtime.jobs.get_job(job.job_id).result)
                assert native_case.source_guard_snapshot()==source_before
                summary.update(complete=True,packet_sha256=hashlib.sha256(state['native_packet']).hexdigest(),
                    packet_bytes=len(state['native_packet']),view_sha256=hashlib.sha256(wire.canonical(view)).hexdigest(),
                    jobs=len(runtime.jobs.list_jobs()),attempts=len(runtime.attempts.list_attempts()),
                    provider_processes=0,inert_model_processes=len(processes),source_prepares=1,
                    runtime_heartbeats=sum(e.event_type=='ATTEMPT_HEARTBEAT' for e in runtime.events.list_events()),
                    completed_same_original_read=True,access_advance_read=True,corrupt_original_refused=True)
                checkpoint()
            finally:
                in_linux(generator.close)
    assert native_case.source_guard_snapshot()==original_source_before
