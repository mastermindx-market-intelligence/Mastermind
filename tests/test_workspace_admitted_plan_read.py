"""Admitted-plan read through real Runtime, Workspace, socket and signed HTTP.

All owners and peer identities are test fixtures; no installed or provider proof.
"""
import asyncio
from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
import json

import httpx
import pytest

from control_plane import executive_runtime as er
from control_plane.workspace_read_service import WorkspaceReadService
from common import executive_workspace_contract as wire
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.contract import (
    BINDINGS_SCHEMA, principal_frame, workspace_authorizers,
)
from integrations.executive_mcp.server import (
    AuditedWorkspaceApp, build_executive_mcp_app, _mounted_lifespan,
)
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.gateway import AppPolicies
from scripts import chairman_control_room as ccr
from tests.test_runtime_admitted_plan_read import _bound, _active
from tests.test_executive_terminal_return import _completed_planner
from tests.test_workspace_read_service import cache_fixture, frame
from tests.test_mission_workspace import _owner_observation_inputs
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW
from tests.test_workspace_read_socket import control, short_socket_root
from tests.test_mastermind_executive_app_asgi import _read_policy, _submit_policy, _FakeJwksCache

SCHEMA = 'mastermind.executive_workspace_read.v3'
BODY = 'mastermind.workspace_admitted_execution_plan.v1'
OBSERVATION = 'mastermind.workspace_plan_observation.v1'
ROUTE = '/workspace/plan/current'


@contextmanager
def owner_fixture(tmp_path, kind='completed'):
    if kind == 'completed':
        writer, planner, attempt = _completed_planner(tmp_path / 'runtime')
        root_id = planner.root_job_id
    else:
        writer, root_id, planner, attempt = _active(tmp_path / 'runtime', admit=kind == 'active')
    with _bound(writer) as (reader, namespace, binding):
        selected = dict(work_ref='WS:ONE', root_job_id=root_id)
        owners, clock, cache = cache_fixture(tmp_path)
        doc = _owner_observation_inputs()['control_room']
        doc = json.loads(json.dumps(doc).replace('JOB-1', root_id).replace('2026-09-20', '2026-09-21'))
        doc['generated_at'] = owners[0].state_cache['doc']['generated_at']
        doc['autonomy']['generated_at'] = doc['generated_at']
        doc['autonomy']['schema'] = 'mastermind.autonomy_control_room.v1'
        row = doc['autonomy']['responsibilities'][0]
        row['freshness'] = 'current'
        row['validity'] = owners[0].state_cache['doc']['autonomy']['responsibilities'][0]['validity']
        owners[0].state_cache['doc'] = doc
        owners[0].state_cache.pop('source_validity_bounds', None)
        with owners[0].state_lock:
            ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
        yield dict(writer=writer, reader=reader, namespace=namespace, binding=binding,
                   owners=owners, clock=clock, cache=cache, selection=selected)


@pytest.fixture
def plan_owner(tmp_path):
    with owner_fixture(tmp_path) as owner:
        yield owner


def request(owner):
    value = frame()
    value.update(schema=SCHEMA, operation='admitted_plan', selection=dict(owner['selection']))
    return value


def service(owner, authorize=lambda p: True):
    return WorkspaceReadService(cache=owner['cache'], runtime=owner['writer'],
        authorize=authorize, armed={}, runtime_identity={'db_present': True},
        bounded_runtime=lambda actual: owner['reader'] if actual is owner['writer'] else pytest.fail('wrong Runtime'))


def call(owner, **kwargs):
    return asyncio.run(service(owner, **kwargs).handle_frame(request(owner)))


def assert_unavailable(envelope, reason):
    assert set(envelope) == {'ok', 'result'} and envelope['ok'] is True
    body = envelope['result']
    assert set(body) == {'schema', 'selection', 'availability', 'reason_codes', 'source_observation', 'plan'}
    assert body['schema'] == BODY and body['availability'] == 'UNAVAILABLE'
    assert body['reason_codes'] == [reason] and body['plan'] is None
    observation = body['source_observation']
    assert observation == dict(schema=OBSERVATION, selection=body['selection'],
        state='CONFLICT' if reason == 'SOURCE_CHANGED' else 'UNKNOWN', control_room=None, runtime=None)
    assert len(wire.canonical(envelope)) + 1 <= 16384


@pytest.mark.parametrize('kind', ['completed', 'active'])
def test_real_admission_read_is_closed_before_projection(tmp_path, monkeypatch, kind):
    from control_plane import fabric_plan_projection as projection
    with owner_fixture(tmp_path, kind) as owner:
        seen = []
        original = projection.project_admitted_plan
        def project(snapshot, receipt):
            assert not owner['namespace'].active
            assert owner['namespace'].entries == owner['namespace'].exits
            assert receipt.state == 'SAME'
            result = original(snapshot, receipt)
            seen.append((snapshot, receipt, result))
            return result
        monkeypatch.setattr(projection, 'project_admitted_plan', project)
        before = owner['namespace'].entries
        envelope = call(owner)
        body = envelope['result']
        assert body['availability'] == 'AVAILABLE' and body['reason_codes'] == []
        assert body['schema'] == BODY and body['selection'] == owner['selection']
        assert len(seen) == 1 and body['plan'] == seen[0][2]
        assert body['source_observation']['runtime'] == seen[0][1].to_dict()
        assert body['source_observation']['schema'] == OBSERVATION
        assert body['source_observation']['state'] == 'SAME'
        assert owner['namespace'].entries == before + 1 == owner['namespace'].exits
        assert len(wire.canonical(envelope)) + 1 <= 16384


def test_proposal_without_admission_stays_unavailable(tmp_path):
    with owner_fixture(tmp_path, 'proposal') as owner:
        assert_unavailable(call(owner), 'ADMISSION_NOT_ESTABLISHED')


def test_missing_selection_is_404_before_runtime(plan_owner):
    owner = plan_owner
    owner['owners'][0].state_cache['doc']['work'] = []
    before = owner['namespace'].entries
    assert call(owner) == wire.error('selection_not_found', 404)
    assert owner['namespace'].entries == before


@pytest.mark.parametrize('mutation', ['owner', 'publication', 'document', 'validity', 'currentness'])
def test_ccr_positive_change_discards_all_material(plan_owner, mutation):
    owner = plan_owner
    original = owner['cache'].snapshot
    count = [0]
    def snapshot():
        result = original()
        count[0] += 1
        if count[0] == 2:
            if mutation == 'owner': result = replace(result, owner=object())
            elif mutation == 'publication': result = replace(result, publication=result.publication + 1)
            elif mutation == 'document': result.document['work'][0]['agent_os']['title'] = 'changed'
            elif mutation == 'validity': result.validity['fixture_changed'] = True
            else: result.currentness['fixture_changed'] = True
        return result
    owner['cache'].snapshot = snapshot
    assert_unavailable(call(owner), 'SOURCE_CHANGED')


@pytest.mark.parametrize('fault,reason', [
    (er.RuntimePlanAdmissionConflict(), 'ADMISSION_CONFLICT'),
    (er.RuntimePlanAdmissionNotEstablished(), 'ADMISSION_NOT_ESTABLISHED'),
    (er.RuntimeRoleResultOverBudget(), 'OVER_BUDGET'),
    (er.RuntimeReadUnavailable('private'), 'SOURCE_UNAVAILABLE'),
    (ValueError('private source path'), 'SOURCE_UNAVAILABLE'),
])
def test_actual_reader_refusals_have_closed_body(plan_owner, monkeypatch, fault, reason):
    def refuse(*args): raise fault
    monkeypatch.setattr(er.BoundedRuntimeReadObservation, 'read_admitted_plan_bounded', refuse)
    assert_unavailable(call(plan_owner), reason)


@pytest.mark.parametrize('fault', ['close', 'policy', 'receipt_conflict', 'receipt_unknown', 'work_ref'])
def test_release_checks_discard_unqualified_material(plan_owner, monkeypatch, fault):
    owner = plan_owner
    observe = er.Runtime.observe_bounded_read
    if fault == 'close':
        original = er.RuntimeStore._close_read_connection
        def close(store, connection):
            original(store, connection)
            if store is owner['reader'].store: raise er.RuntimeReadUnavailable('close uncertain')
        monkeypatch.setattr(er.RuntimeStore, '_close_read_connection', close)
    elif fault == 'work_ref':
        original = er.BoundedRuntimeReadObservation.read_admitted_plan_bounded
        def read(obs, root):
            value = original(obs, root)
            return replace(value, root_metadata=replace(value.root_metadata, work_ref='WS:FOREIGN'))
        monkeypatch.setattr(er.BoundedRuntimeReadObservation, 'read_admitted_plan_bounded', read)
    else:
        @contextmanager
        def observed(runtime):
            with observe(runtime) as observation: yield observation
            if runtime is owner['reader']:
                if fault == 'policy':
                    monkeypatch.setattr(er.CooCyclePolicy, 'load', lambda: (_ for _ in ()).throw(ValueError('policy unavailable')))
                else:
                    state = 'CONFLICT' if fault == 'receipt_conflict' else 'UNKNOWN'
                    # The original observation has physically closed; substitute
                    # only the finalized owner receipt for this boundary fault.
                    observation._receipt = replace(observation.receipt, state=state)
        monkeypatch.setattr(er.Runtime, 'observe_bounded_read', observed)
    assert_unavailable(call(owner), 'SOURCE_CHANGED' if fault == 'receipt_conflict' else 'SOURCE_UNAVAILABLE')


@pytest.mark.parametrize('mutation', ['disabled', 'missing', 'changed'])
def test_permission_reload_after_physical_close(plan_owner, monkeypatch, mutation):
    owner = plan_owner
    authority = {'enabled': True, 'digest': 'a' * 64}
    def authorize(p): return authority['enabled']
    authorize.binding_digest = lambda p: authority['digest']
    original = er.Runtime.observe_bounded_read
    @contextmanager
    def observed(runtime):
        with original(runtime) as observation: yield observation
        if runtime is owner['reader']:
            if mutation == 'disabled': authority['enabled'] = False
            else: authority['digest'] = None if mutation == 'missing' else 'b' * 64
    monkeypatch.setattr(er.Runtime, 'observe_bounded_read', observed)
    assert call(owner, authorize=authorize) == wire.error('access_denied', 403)


@asynccontextmanager
async def transport(owner, key, tmp_path, socket_root, *, after_app=None):
    auth = _authenticator(key)
    token = _workspace_token(key)
    principal = await auth.verify_authorization_header('Bearer ' + token, now=NOW)
    slots = {'schema': BINDINGS_SCHEMA, 'profiles': {
        'web': {'enabled': True, 'binding': dict(principal_frame(principal), permission_digest='a' * 64)},
        'mac': {'enabled': False, 'binding': None}}}
    app_auth, control_auth = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
    seen = {'factory': 0}
    def factory(actual):
        assert actual is owner['writer']
        seen['factory'] += 1
        return service(owner, authorize=control_auth)
    svc = control(owner['writer'].store.root.parent, socket_root, factory)
    svc._runtime_factory = lambda path: owner['writer']
    await svc.start()
    client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
    clock = [NOW]
    class AppClient:
        async def request(self, value):
            result = await client.request(value)
            if after_app: after_app(slots, clock)
            return result
    workspace = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: clock[0],
        authorize_principal=app_auth, client=AppClient()))
    class Sink:
        def __init__(self): self.events = []
        def emit(self, event): self.events.append(event)
    sink = Sink()
    verifier = MastermindTokenVerifier(authenticator=auth, policy=auth.policy, now=lambda: clock[0], audit_sink=sink)
    mounted = build_executive_mcp_app(AppSettings(policies=AppPolicies(read=_read_policy(), submit=_submit_policy()),
        mastermind_root=tmp_path, macro_root_flag=None, environ={}, ceo_ingress_socket_path=svc.ceo_ingress_socket_path,
        read_from_ceo_ingress=True, jwks_cache=_FakeJwksCache(key), clock=lambda: clock[0]),
        audit_sink=sink, workspace_app=AuditedWorkspaceApp(workspace, verifier))
    try:
        async with _mounted_lifespan(mounted):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mounted), base_url='https://mcp.mastermind-x.com') as http:
                yield http, token, slots, seen, client, principal, mounted
    finally:
        await svc.close()


def test_signed_mounted_http_and_actual_dispatcher(plan_owner, rsa_key, tmp_path, short_socket_root):
    owner = plan_owner
    async def run():
        async with transport(owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, client, principal, _):
            response = await http.get(ROUTE, params=owner['selection'], headers={'Authorization': 'Bearer ' + token})
            assert response.status_code == 200, response.text
            assert response.json()['schema'] == BODY
            assert response.json()['availability'] == 'AVAILABLE'
            assert response.headers['cache-control'] == 'no-store'
            value = request(owner)
            value['principal'] = principal_frame(principal)
            socket = await client.request(value)
            assert socket['result']['plan'] == response.json()['plan']
            assert len(wire.canonical(socket)) + 1 <= 16384
            assert seen['factory'] == 2
    asyncio.run(run())


@pytest.mark.parametrize('mutation', ['disabled', 'digest', 'expired'])
def test_http_rechecks_permission_and_expiry(plan_owner, rsa_key, tmp_path, short_socket_root, mutation):
    def after(slots, clock):
        if mutation == 'disabled': slots['profiles']['web']['enabled'] = False
        elif mutation == 'digest': slots['profiles']['web']['binding']['permission_digest'] = 'b' * 64
        else: clock[0] += 86400
    async def run():
        async with transport(plan_owner, rsa_key, tmp_path, short_socket_root, after_app=after) as (http, token, *_):
            response = await http.get(ROUTE, params=plan_owner['selection'], headers={'Authorization': 'Bearer ' + token})
            assert response.status_code == 403
            assert 'plan_digest' not in response.text
    asyncio.run(run())


@pytest.mark.parametrize('schema', [wire.FRAME_SCHEMA, wire.FRAME_SCHEMA_V2])
def test_old_protocols_do_not_accept_new_operation(plan_owner, schema):
    value = request(plan_owner)
    value['schema'] = schema
    before = plan_owner['namespace'].entries
    assert asyncio.run(service(plan_owner).handle_frame(value)) == wire.error('invalid_input', 400)
    assert plan_owner['namespace'].entries == before


@pytest.mark.parametrize('mutation', ['wrong_operation', 'extra_frame', 'extra_selection', 'missing_root',
    'wrong_resource', 'submit_scope', 'wrong_principal', 'bad_work', 'bool_root'])
def test_v3_contract_rejects_before_acquisition(plan_owner, mutation):
    value = request(plan_owner)
    if mutation == 'wrong_operation': value['operation'] = 'result'
    elif mutation == 'extra_frame': value['budget'] = 1000000
    elif mutation == 'extra_selection': value['selection']['attempt_id'] = 'ATT-001'
    elif mutation == 'missing_root': value['selection'].pop('root_job_id')
    elif mutation == 'wrong_resource': value['principal']['resource'] = 'https://wrong.invalid'
    elif mutation == 'submit_scope': value['principal']['scopes'] = ['mastermind.executive.intent.submit']
    elif mutation == 'wrong_principal': value['principal'] = None
    elif mutation == 'bad_work': value['selection']['work_ref'] = '../private'
    else: value['selection']['root_job_id'] = True
    before = plan_owner['namespace'].entries
    assert asyncio.run(service(plan_owner).handle_frame(value)) == wire.error('invalid_input', 400)
    assert plan_owner['namespace'].entries == before


def test_actual_composition_uses_one_select_and_no_database_writes(plan_owner, monkeypatch):
    traces = []
    original = er.sqlite3.connect
    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        connection.set_trace_callback(traces.append)
        return connection
    monkeypatch.setattr(er.sqlite3, 'connect', connect)
    for registry, name in [(plan_owner['reader'].jobs, 'list_jobs'),
        (plan_owner['reader'].attempts, 'list_attempts'), (plan_owner['reader'].events, 'list_events')]:
        monkeypatch.setattr(registry, name, lambda *a, **k: pytest.fail('unbounded list acquisition'))
    body = call(plan_owner)['result']
    assert body['availability'] == 'AVAILABLE'
    statements = [sql.strip().upper() for sql in traces]
    assert statements.count('PRAGMA DATA_VERSION') == 2
    assert not any(sql.startswith(('INSERT', 'UPDATE', 'DELETE')) for sql in statements)


@pytest.mark.parametrize('size', [16383, 16384, 16385])
def test_entire_socket_wrapper_and_lf_budget(plan_owner, monkeypatch, size):
    from control_plane import fabric_plan_projection as projection
    original = projection.project_admitted_plan
    initial = call(plan_owner)['result']
    assert initial['availability'] == 'AVAILABLE'
    initial_size = len(wire.canonical({'ok': True, 'result': initial})) + 1
    # Only projection payload length changes; this fault injection deliberately
    # tests the OUTER ceiling, independently of the pure text limit.
    def project(snapshot, receipt):
        value = original(snapshot, receipt)
        value['steps'][0]['objective'] += 'x' * (size - initial_size)
        return value
    monkeypatch.setattr(projection, 'project_admitted_plan', project)
    result = call(plan_owner)
    if size <= 16384:
        assert result['result']['availability'] == 'AVAILABLE'
        assert len(wire.canonical(result)) + 1 == size
    else:
        assert_unavailable(result, 'RESPONSE_OVER_BUDGET')


@pytest.mark.parametrize('bad_token', ['missing', 'foreign_client', 'executive_scope', 'foreign_subject'])
def test_mounted_http_authorizes_before_factory(plan_owner, rsa_key, tmp_path, short_socket_root, bad_token):
    async def run():
        async with transport(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            if bad_token == 'missing': headers = {}
            else:
                kwargs = {'client_id': 'foreign'} if bad_token == 'foreign_client' else (
                    {'scope': 'mastermind.executive.read'} if bad_token == 'executive_scope' else {'sub': 'foreign'})
                headers = {'Authorization': 'Bearer ' + _workspace_token(rsa_key, **kwargs)}
            response = await http.get(ROUTE, params=plan_owner['selection'], headers=headers)
            assert response.status_code in (401, 403)
            assert seen['factory'] == 0
    asyncio.run(run())


@pytest.mark.parametrize('fault', ['extra_query', 'duplicate_query', 'missing_query', 'body', 'post', 'trailing_slash'])
def test_mounted_http_input_is_closed(plan_owner, rsa_key, tmp_path, short_socket_root, fault):
    async def run():
        async with transport(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            query = list(plan_owner['selection'].items())
            path, method, body = ROUTE, 'GET', b''
            if fault == 'extra_query': query.append(('history', 'all'))
            elif fault == 'duplicate_query': query.append(('work_ref', 'WS:OTHER'))
            elif fault == 'missing_query': query = []
            elif fault == 'body': body = b'x'
            elif fault == 'post': method = 'POST'
            else: path += '/'
            response = await http.request(method, path, params=query, content=body,
                headers={'Authorization': 'Bearer ' + token})
            assert response.status_code in (400, 404, 405), response.text
            assert seen['factory'] == 0
    asyncio.run(run())


@pytest.mark.parametrize('elapsed,expected', [(1, 'AVAILABLE'), (61000, 'SOURCE_UNAVAILABLE')])
def test_canonical_validity_clock_ages_without_false_generation_change(plan_owner, elapsed, expected):
    owner = plan_owner
    original = owner['cache'].snapshot
    calls = [0]
    def snapshot():
        calls[0] += 1
        if calls[0] == 2:
            owner['clock'][:] = [value + elapsed for value in owner['clock']]
        return original()
    owner['cache'].snapshot = snapshot
    envelope = call(owner)
    if expected == 'AVAILABLE':
        assert envelope['result']['availability'] == expected
    else:
        assert_unavailable(envelope, expected)


def _transport_frame():
    value = frame()
    value.update(schema=SCHEMA, operation='admitted_plan')
    return value


@pytest.mark.parametrize('size', [16383, 16384, 16385])
@pytest.mark.parametrize('unicode', [False, True])
def test_real_dispatcher_plan_whole_utf8_boundary(tmp_path, short_socket_root, size, unicode):
    from tests.test_workspace_result_socket import control as make_control, _FakeProvider
    envelope = {'ok': True, 'result': {'padding': '漢' if unicode else ''}}
    envelope['result']['padding'] += 'x' * (size - len(wire.canonical(envelope)) - 1)
    async def run():
        svc = make_control(tmp_path, short_socket_root, lambda _: _FakeProvider(envelope))
        await svc.start()
        try:
            result = await CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path).request(_transport_frame())
            if size <= 16384: assert result == envelope
            else: assert_unavailable(result, 'RESPONSE_OVER_BUDGET')
        finally: await svc.close()
    asyncio.run(run())


def test_client_validates_new_frame_before_socket_and_uses_fixed_limit(monkeypatch):
    seen = []
    async def open_socket(*args, **kwargs):
        seen.append(kwargs['limit'])
        raise OSError('fixture transport unavailable')
    monkeypatch.setattr(asyncio, 'open_unix_connection', open_socket)
    client = CeoIngressWorkspaceClient('/tmp/fixture-does-not-open.sock')
    value = _transport_frame()
    value['operation'] = 'mission_v3'
    with pytest.raises(ValueError): asyncio.run(client.request(value))
    assert seen == []
    with pytest.raises(ValueError): asyncio.run(client.request(_transport_frame()))
    assert seen == [16384]


def test_actual_dispatcher_rejects_invalid_v3_before_owner_factory(tmp_path, short_socket_root):
    from tests.test_workspace_result_socket import control as make_control
    def forbidden(_): pytest.fail('malformed v3 reached owner factory')
    async def run():
        svc = make_control(tmp_path, short_socket_root, forbidden)
        await svc.start()
        try:
            # Deliberately bypass the client validator to exercise the server.
            reader, writer = await asyncio.open_unix_connection(str(svc.ceo_ingress_socket_path))
            try:
                value = _transport_frame(); value['operation'] = 'result'
                writer.write(wire.canonical(value) + b'\n'); await writer.drain()
                result = json.loads(await reader.readuntil(b'\n'))
                assert result == wire.error('invalid_input', 400)
            finally:
                writer.close(); await writer.wait_closed()
        finally: await svc.close()
    asyncio.run(run())


@pytest.mark.parametrize('kind', ['oversized', 'selection', 'null_proof', 'extra_body'])
def test_http_edge_refuses_malformed_or_oversized_plan(plan_owner, kind):
    from integrations.mastermind_workspace_app.app import _plan_envelope_response
    envelope = call(plan_owner)
    assert envelope['result']['availability'] == 'AVAILABLE'
    if kind == 'oversized': envelope['result']['plan']['steps'][0]['objective'] = 'x' * 16384
    elif kind == 'selection': envelope['result']['source_observation']['selection']['work_ref'] = 'WS:FOREIGN'
    elif kind == 'null_proof': envelope['result']['source_observation']['runtime'] = None
    else: envelope['result']['extra'] = 'private'
    response = _plan_envelope_response(envelope)
    assert response.status_code == 503
    body = json.loads(response.body)
    if kind == 'oversized': assert_unavailable({'ok': True, 'result': body}, 'RESPONSE_OVER_BUDGET')
    else: assert 'plan_digest' not in response.body.decode()


@pytest.mark.parametrize('objective,reason', [
    ('Bearer fixture-private-token', 'CONTENT_WITHHELD'),
    ('x' * 4097, 'CONTENT_OVER_BUDGET'),
])
def test_review_display_refusals_reach_signed_http(plan_owner, rsa_key, tmp_path,
                                                   short_socket_root, monkeypatch,
                                                   objective, reason):
    from control_plane import fabric_plan_projection as projection
    original = projection.project_admitted_plan
    seen = []
    def project(snapshot, receipt):
        # Inject display-only material after the actual admission/close boundary;
        # retain the real projector and the complete outer transport composition.
        assert not plan_owner['namespace'].active
        assert receipt.state == 'SAME'
        snapshot.plan['steps'][0]['objective'] = objective
        seen.append(receipt)
        return original(snapshot, receipt)
    monkeypatch.setattr(projection, 'project_admitted_plan', project)
    async def run():
        async with transport(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, *_):
            response = await http.get(ROUTE, params=plan_owner['selection'],
                                      headers={'Authorization': 'Bearer ' + token})
            assert response.status_code == 503
            assert_unavailable({'ok': True, 'result': response.json()}, reason)
            assert objective not in response.text
            assert len(seen) == 1
    asyncio.run(run())


@pytest.mark.parametrize("path,replacement", [
    (("runtime",), {}),
    (("control_room",), {}),
    (("runtime", "state"), "CONFLICT"),
    (("runtime", "state"), "UNKNOWN"),
    (("runtime", "schema"), "wrong"),
    (("runtime", "source_identity"), None),
    (("runtime", "source_identity"), "not-a-request-identity"),
    (("runtime", "before"), -1),
    (("runtime", "after"), -1),
    (("runtime", "before"), True),
    (("runtime", "after"), True),
    (("runtime", "after"), 1.0),
    (("runtime", "extra"), "private-receipt-marker"),
    (("control_room", "instance_before"), None),
    (("control_room", "instance_after"), "different-owner-instance"),
    (("control_room", "publication_before"), 0),
    (("control_room", "publication_after"), 0),
    (("control_room", "publication_before"), True),
    (("control_room", "publication_after"), True),
    (("control_room", "publication_after"), 1.0),
    (("control_room", "document_digest"), "invalid"),
    (("control_room", "source_validity_digest"), None),
    (("control_room", "cache_currentness_digest"), "A" * 64),
    (("control_room", "extra"), "private-receipt-marker"),
])
def test_http_edge_refuses_unqualified_plan_receipt(plan_owner, path, replacement):
    from integrations.mastermind_workspace_app.app import _plan_envelope_response
    envelope = call(plan_owner)
    assert envelope["result"]["availability"] == "AVAILABLE"
    target = envelope["result"]["source_observation"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    response = _plan_envelope_response(envelope)
    assert response.status_code == 503
    assert "plan_digest" not in response.body.decode()
    assert "private-receipt-marker" not in response.body.decode()


@pytest.mark.parametrize("reason", sorted(wire.PLAN_REFUSAL_REASONS))
def test_http_edge_preserves_canonical_plan_unavailable(reason):
    from integrations.mastermind_workspace_app.app import _plan_envelope_response
    envelope = wire.plan_unavailable(
        {"work_ref": "WS:RECEIPT-PROOF", "root_job_id": "JOB-123"}, reason)
    response = _plan_envelope_response(envelope)
    assert response.status_code == 503
    assert json.loads(response.body) == envelope["result"]
