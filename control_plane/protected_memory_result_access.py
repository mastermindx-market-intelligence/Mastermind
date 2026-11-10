"""Closed prospective SERVICE read policy inside existing Control config.

Policy is not an original-recipient issuer. Current root/Control identity,
authoritative original receipts and fresh Linux v3 permission remain separate.
No end user, native label, owner_seat or parsed fact is promoted to authority.
"""
from __future__ import annotations
import json
import hashlib
import os
import time
from common import memory_native_wire as wire

SCHEMA='mastermind.memory_original_result_service_access.v1'


def validate_access_document(value):
    wire.exact(value,'schema receiver_kind principal_ref ssh_key_fingerprint control_service_label permissions scope not_before_seconds expires_at_seconds')
    if (value['schema']!=SCHEMA or value['receiver_kind']!='native_broker_service'
            or value['control_service_label']!='com.mastermind.executive.control'
            or value['permissions']!=['read_original_child_result']):
        wire.fail()
    scope=value['scope']
    wire.exact(scope,'operation_id native_root_id native_operator_run_id native_child_run_id job_id root_job_id parent_job_id attempt_id pre_input_sha256 input_sha256 result_sha256')
    for key in ('operation_id','native_root_id','native_operator_run_id','native_child_run_id','job_id','root_job_id','attempt_id'):wire.token(scope[key])
    if scope['parent_job_id'] is not None:wire.token(scope['parent_job_id'])
    for key in ('pre_input_sha256','input_sha256','result_sha256'):wire.digest(scope[key])
    wire._reference(value['principal_ref']);wire.fingerprint(value['ssh_key_fingerprint'])
    for key in ('not_before_seconds','expires_at_seconds'):wire.integer(value[key],100_000_000_000)
    if not 0<value['expires_at_seconds']-value['not_before_seconds']<=14400:wire.fail()
    return json.loads(wire.canonical(value))


def _material(value):
    wire.exact(value,'namespace reference pre_input case')
    ref=value['reference'];case=value['case'];projection=value['pre_input']
    wire.exact(ref,'schema operation_id job_id root_job_id parent_job_id attempt_id pre_input_sha256 input_sha256 input_bytes result_sha256 result_bytes receipt_event_ids original_recipient disclosure_authorized retry_authorized wire_version')
    if (ref['schema']!='mastermind.memory_completed_original_reference.v2' or ref['wire_version']!='v3'
            or ref['disclosure_authorized'] is not False or ref['retry_authorized'] is not False):wire.fail()
    for key in ('operation_id','job_id','root_job_id','attempt_id'):wire.token(ref[key])
    if ref['parent_job_id'] is not None:wire.token(ref['parent_job_id'])
    for key in ('pre_input_sha256','input_sha256','result_sha256'):wire.digest(ref[key])
    for key in ('input_bytes','result_bytes'):wire.integer(ref[key],65536)
    ids=ref['receipt_event_ids']
    if (type(ids) is not list or len(ids)!=6 or any(type(i) is not int or i<=0 for i in ids)
            or ids!=sorted(set(ids))):wire.fail()
    from control_plane import protected_memory_peer as peer
    peer._projection_shape(projection)
    bound=projection['runtime_admission']
    if (hashlib.sha256(peer.canonical(projection)).hexdigest()!=ref['pre_input_sha256']
            or projection['original_operation_id']!=ref['operation_id']
            or any(bound[k]!=ref[v] for k,v in (('job_id','job_id'),('runtime_root','root_job_id'),
                ('parent_job_id','parent_job_id'),('attempt_id','attempt_id')))):wire.fail()
    wire.exact(case,'schema attempt_id pre_input_sha256 operation_id wire_version intent issuer locator')
    if (case['schema']!='mastermind.memory_original_case_binding.v1' or case['wire_version']!='v3'
            or case['attempt_id']!=ref['attempt_id'] or case['pre_input_sha256']!=ref['pre_input_sha256']
            or case['operation_id']!=ref['operation_id']
            or case['intent']!=dict(projection['native_source_locator'],participant_binding_sha256=ref['pre_input_sha256'])):wire.fail()
    wire._issuer(case['issuer'],'v3');wire.locator(case['locator'])
    if (case['locator']['input_sha256']!=ref['input_sha256'] or case['locator']['input_bytes']!=ref['input_bytes']):wire.fail()
    request=wire.validate_request({'schema':'research_factory.market_memory_e0_native_issuer_request.v3',
        'action':'authorize_result_disclosure','operation_id':ref['operation_id'],'intent':case['intent'],
        'locator':case['locator'],'result_ref':{k:ref[k] for k in ('attempt_id','input_sha256','result_sha256','result_bytes')}})
    wire.original_recipient(ref['original_recipient'],request=request,issuer=case['issuer'])
    return ref,request


def _current_policy(observed,material,enrollment):
    from control_plane import executive_memory_issuer as issuer
    from control_plane.protected_memory_profile import _json
    raw=issuer._read(issuer.CONFIG,4194304)
    if hashlib.sha256(raw).hexdigest()!=observed['configuration_sha256']:wire.fail()
    config=_json(raw)
    if (type(material['namespace']) is not str or config.get('runtime_root')!=material['namespace']):wire.fail()
    policy=validate_access_document(config.get('memory_original_result_access'))
    now=time.time()
    recipient=material['reference']['original_recipient']
    ref=material['reference'];native=material['pre_input']['native_source_locator']
    expected_scope={k:ref[k] for k in ('operation_id','job_id','root_job_id','parent_job_id','attempt_id','pre_input_sha256','input_sha256','result_sha256')}
    expected_scope.update(native_root_id=native['root_id'],native_operator_run_id=native['operator_run_id'],native_child_run_id=native['child_run_id'])
    if (not policy['not_before_seconds']<=now<policy['expires_at_seconds']
            or policy['scope']!=expected_scope
            or policy['principal_ref']!=recipient['principal_ref']
            or policy['ssh_key_fingerprint']!=recipient['ssh_key_fingerprint']
            or enrollment[1]!=recipient['ssh_key_fingerprint']
            or observed['service_label']!=policy['control_service_label']):wire.fail()
    return raw


def authorize_completed_read(connection,material):
    """Actual current SERVICE receiver, independent of original active lease.

    Material comes only from the source-qualified current Control's nominal
    Runtime receipt loader, never a public caller selector. Root independently
    checks that namespace, current service policy/key and fresh Linux grant.
    """
    if os.geteuid()!=0:wire.fail()
    from control_plane import protected_memory_peer as peer
    from control_plane import executive_memory_issuer as issuer
    observed=peer.observe_control_owner(connection)
    ref,request=_material(material)
    before=issuer._enrollment(observed)
    if issuer._protocol(before)!='memory.e0.native_issuer.v3':wire.fail()
    policy=_current_policy(observed,material,before)
    response=wire.decode_response(issuer._exchange(wire.encode_request(request)),request=request)
    if response.get('status')!='RESULT_DISCLOSURE_CURRENT':wire.fail()
    previous=material['case']['issuer'];current=response['issuer']
    if any(previous[k]!=current[k] for k in set(previous)-{'current_selection_sha256','current_access_ref'}):wire.fail()
    if response['authorization']['original_recipient']!=ref['original_recipient']:wire.fail()
    if (peer.observe_control_owner(connection)!=observed or issuer._enrollment(observed)!=before
            or _current_policy(observed,material,before)!=policy):wire.fail()
    return {'schema':'mastermind.memory_completed_service_read_current.v1',
        'reference_sha256':hashlib.sha256(wire.canonical(ref)).hexdigest(),'owner':observed,
        'receiver_kind':'native_broker_service','retry_authorized':False}
