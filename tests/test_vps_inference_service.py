"""Hermetic service edge and client contract; no installed hosts or providers."""
import asyncio
import dataclasses
import json

import httpx
import pytest

from control_plane import ceo_intent, executive_service_principal as esp
from control_plane.executive_runtime import Runtime
from tests import test_mastermind_executive_app_asgi as auth

rsa_key = auth.rsa_key


def host_execution_binding(root, identity):
    from control_plane.executive_inference_execution import build_execution_binding
    return build_execution_binding(
        intent_id=identity,
        workspace_root=root,
        base_sha="a" * 40,
        eligible_quota_classes=("fixture",),
    )


def test_closed_inference_principal_and_sink(tmp_path):
    principal = esp.service_principal('svc-vps-inference')
    assert set(esp.REGISTRY) == {'svc-site-maintenance', 'svc-vps-inference'}
    assert ceo_intent.SERVICE_PRINCIPAL_BINDINGS == frozenset((p.principal_id, p.actor) for p in esp.REGISTRY.values())
    assert principal.owner_seat == principal.escalation_target == 'coo'
    assert principal.allowed_operations == {'READ', 'RESEARCH'}
    with pytest.raises(esp.ServicePrincipalRefused):
        esp.service_principal('svc-unreviewed')


def test_ingress_replay_conflict_and_status(tmp_path):
    from control_plane import executive_inference_ingress as service
    from control_plane.executive_ceo_ingress import CeoIngressError
    from control_plane.executive_inference_contract import intent_id
    rt = Runtime.at(tmp_path / 'runtime')
    ground = GROUND
    class Ground:
        def observe(self): return ground
    request = {'operation_key': 'inference-test', 'objective': 'Summarize the supplied research.'}
    frame = dict(schema=service.SUBMIT_SCHEMA, request=request, observed_grounding=ground)
    async def run():
        kw = dict(
            runtime=rt, grounding_provider=Ground(), workspace_root=tmp_path,
            admission_guard=lambda _: None,
            execution_binding_provider=lambda identity: host_execution_binding(tmp_path, identity),
        )
        first = await service.handle_frame(frame, **kw)
        second = await service.handle_frame(
            frame,
            **dict(
                kw,
                admission_guard=None,
                execution_binding_provider=lambda _:
                    pytest.fail("accepted duplicate must not re-run host routing"),
            ),
        )
        assert first['job_id'] == second['job_id'] and second['duplicate'] is True
        assert first['intent_id'] == intent_id(request['operation_key'])
        with pytest.raises(CeoIngressError) as conflict:
            await service.handle_frame(dict(frame, request=dict(request, objective='Different research')), **kw)
        assert conflict.value.code == 'operation_conflict'
        receipt = await service.handle_frame(dict(schema=service.STATUS_SCHEMA, operation_key=request['operation_key']), **dict(kw, admission_guard=None))
        assert receipt['receipt']['job_id'] == first['job_id']
        assert receipt['terminal_result_ref'] is None
        job = rt.jobs.get_job(first['job_id'])
        assert job.owner_seat == 'coo' and not job.allowed_write_paths and not job.validation_commands
        assert job.worktree == str(tmp_path / first['intent_id'])
        assert job.branch == 'codex/' + first['intent_id']
        assert job.constraints['base_sha'] == 'a' * 40
        assert job.constraints['eligible_quota_classes'] == ['fixture']
        assert job.constraints['task_kind'] == 'research'
        assert job.constraints['preferred_model_aliases']
        assert len(rt.jobs.list_jobs()) == 1
    asyncio.run(run())


def test_execution_binding_is_host_derived_and_route_closed(tmp_path):
    from control_plane.executive_inference_contract import intent_id
    from control_plane.executive_inference_execution import (
        InferenceExecutionBindingError,
        validate_execution_binding,
    )
    identity = intent_id("binding-policy")
    binding = host_execution_binding(tmp_path, identity)
    assert binding["schema"] == "mastermind.executive_service_inference_binding.v1"
    assert binding["intent_id"] == identity
    assert binding["worktree"] == str(tmp_path / identity)
    assert binding["branch"] == "codex/" + identity
    assert binding["constraints"]["task_kind"] == "research"
    assert binding["constraints"]["risk"] == "routine"
    assert binding["constraints"]["ambiguity"] == "low"
    assert binding["constraints"]["required_capabilities"] == ["research"]
    assert binding["constraints"]["eligible_quota_classes"] == ["fixture"]
    assert "provider" not in binding["constraints"]
    assert validate_execution_binding(
        binding, intent_id=identity, workspace_root=tmp_path
    ) == binding
    forged = dict(binding, worktree=str(tmp_path / "foreign"))
    with pytest.raises(InferenceExecutionBindingError):
        validate_execution_binding(
            forged, intent_id=identity, workspace_root=tmp_path
        )

    for key, value in (
        ("preferred_model_aliases", ["forged.research"]),
        ("required_capabilities", []),
        ("routing_policy_version", "forged.route"),
        ("execution_profile_digest", "0" * 64),
    ):
        constraints = dict(binding["constraints"])
        constraints[key] = value
        forged_route = dict(binding, constraints=constraints)
        with pytest.raises(InferenceExecutionBindingError):
            validate_execution_binding(
                forged_route, intent_id=identity, workspace_root=tmp_path
            )


@pytest.mark.parametrize(("field", "value"), [
    ("intent_id", None),
    ("intent_id", True),
    ("base_sha", None),
    ("base_sha", True),
    ("eligible_quota_classes", (None,)),
    ("eligible_quota_classes", (True,)),
])
def test_execution_binding_requires_exact_host_scalar_types(tmp_path, field, value):
    from control_plane.executive_inference_execution import (
        InferenceExecutionBindingError,
        build_execution_binding,
    )
    kwargs = {
        "intent_id": "service-inference-type-negative",
        "workspace_root": tmp_path,
        "base_sha": "1" * 40,
        "eligible_quota_classes": ("fixture",),
    }
    kwargs[field] = value
    with pytest.raises(InferenceExecutionBindingError):
        build_execution_binding(**kwargs)


def test_service_binding_drives_runtime_capacity_without_provider_override(tmp_path):
    from control_plane import executive_inference_ingress as service
    from control_plane.model_router import ModelRouter

    rt = Runtime.at(tmp_path / "runtime")
    router = ModelRouter.load()

    def register(worker_id, model_alias, quota_class):
        profile = router.resolve_model_alias(model_alias)
        rt.workers.register_worker(
            worker_id,
            provider=profile.provider_alias,
            account_label=f"account-{worker_id}",
            worker_type=profile.adapter_id,
            capabilities=list(profile.capabilities),
            quota_classes={
                quota_class: {
                    "provider": profile.provider_alias,
                    "model": profile.model,
                    "effort": profile.effort,
                    "cost_class": profile.cost_class,
                    "capabilities": list(profile.capabilities),
                    "metadata": {
                        "adapter_id": profile.adapter_id,
                        "model_alias": profile.model_alias,
                        "provider_alias": profile.provider_alias,
                        "routing_policy_version": router.policy_version,
                        "execution_profile_id": profile.execution_profile_id,
                        "execution_profile_digest": profile.execution_profile_digest,
                        "capability_policy_version": profile.capability_policy_version,
                        "capability_policy_digest": profile.capability_policy_digest,
                    },
                }
            },
        )

    register("fast-research-other", "fast.research", "other")
    register("standard-research", "standard.research", "fixture")
    register("engineering-fixture", "fast.engineering", "fixture")

    class Ground:
        def observe(self):
            return GROUND

    receipt = asyncio.run(service.handle_frame(
        {
            "schema": service.SUBMIT_SCHEMA,
            "request": {
                "operation_key": "capacity-selection",
                "objective": "Research the bounded question.",
            },
            "observed_grounding": GROUND,
        },
        runtime=rt,
        grounding_provider=Ground(),
        workspace_root=tmp_path,
        admission_guard=lambda _: None,
        execution_binding_provider=lambda identity: host_execution_binding(
            tmp_path, identity
        ),
    ))
    job = rt.jobs.get_job(receipt["job_id"])
    assert job is not None
    assert "provider" not in job.constraints and "model" not in job.constraints
    selected = rt.broker.select_worker(job)
    assert selected is not None
    assert selected.worker_id == "standard-research"
    lease = rt.broker.claim(job.job_id)
    assert lease is not None
    assert lease.attempt.worker_id == "standard-research"
    assert lease.attempt.quota_class == "fixture"


@pytest.mark.parametrize("fault", ["missing", "async", "forged"])
def test_fresh_ingress_refuses_untrusted_execution_binding(tmp_path, fault):
    from control_plane import executive_inference_ingress as service
    from control_plane.executive_ceo_ingress import CeoIngressError
    rt = Runtime.at(tmp_path / "runtime")
    class Ground:
        def observe(self): return GROUND
    provider = None
    if fault == "async":
        async def provider(_):
            return host_execution_binding(tmp_path, "service-inference-invalid")
    elif fault == "forged":
        def provider(identity):
            value = host_execution_binding(tmp_path, identity)
            return dict(value, worktree=str(tmp_path / "foreign"))
    with pytest.raises(CeoIngressError):
        asyncio.run(service.handle_frame(
            dict(
                schema=service.SUBMIT_SCHEMA,
                request={"operation_key":"binding-refusal", "objective":"Research"},
                observed_grounding=GROUND,
            ),
            runtime=rt,
            grounding_provider=Ground(),
            workspace_root=tmp_path,
            admission_guard=lambda _: None,
            execution_binding_provider=provider,
        ))
    assert rt.jobs.list_jobs() == []


@pytest.mark.parametrize("frame", [
    [],
    {"schema": []},
    {"schema": "mastermind.ceo_ingress.service_inference_submit.v1",
     "request": {"operation_key": "x", "objective": "Research"},
     "observed_grounding": {"mastermind_sha":"1"*40, "macro_sha":"2"*40,
                            "boot_packet_schema":"mastermind.ceo_boot_packet.v1"}},
    {"schema": "mastermind.ceo_ingress.service_inference_submit.v1",
     "request": {"operation_key": "inference-test", "objective": "x" * 4001},
     "observed_grounding": {"mastermind_sha":"1"*40, "macro_sha":"2"*40,
                            "boot_packet_schema":"mastermind.ceo_boot_packet.v1"}},
])
def test_ingress_malformed_frames_use_typed_invalid_input(tmp_path, frame):
    from control_plane import executive_inference_ingress as service
    from control_plane.executive_ceo_ingress import CeoIngressError
    rt = Runtime.at(tmp_path / "runtime")
    class Ground:
        def observe(self): return GROUND
    with pytest.raises(CeoIngressError) as error:
        asyncio.run(service.handle_frame(
            frame, runtime=rt, grounding_provider=Ground(), workspace_root=tmp_path,
            admission_guard=lambda _: None))
    assert error.value.code == "invalid_input"
    assert rt.jobs.list_jobs() == []


def setup_app(rsa_key, tmp_path):
    from integrations.mastermind_executive_app.inference import InferenceSettings, create_inference_app, SERVICE_SCOPE
    from integrations.mastermind_executive_app.app import AppSettings
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    from integrations.mastermind_executive_app.coo_binding import principal_frame
    policy = auth._read_policy(policy_id='executive-vps-inference', required_scopes=[SERVICE_SCOPE],
        allowed_subject_digests=[auth.subject_digest(issuer=auth.ISSUER, subject='service-vps')])
    cache = auth._FakeJwksCache(rsa_key)
    token = auth._token(rsa_key, scope=SERVICE_SCOPE, sub='service-vps')
    principal = asyncio.run(JwtAuthenticator(policy=policy, jwks_cache=cache).verify_token(token, now=auth.NOW))
    binding = dict(principal_frame(principal), principal_id='svc-vps-inference', principal_kind='service')
    current = {'binding': binding}
    base = AppSettings(policies=AppPolicies(auth._read_policy(), auth._submit_policy()), mastermind_root=tmp_path,
        macro_root_flag=None, environ={}, ceo_ingress_socket_path=tmp_path/'absent.sock',
        read_from_ceo_ingress=True, jwks_cache=cache, clock=lambda: auth.NOW)
    class Audit:
        def emit(self, event):
            from integrations.business_mcp_auth.contracts import AuthErrorCode
            assert event.code in {'accepted', *(code.value for code in AuthErrorCode)}
            assert event.accepted == (event.code == 'accepted')
    app = create_inference_app(InferenceSettings(base, policy, lambda: current['binding']), audit_sink=Audit())
    return app, token, current


async def call(app, token, name, arguments):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        return await client.post('/v1/tools/'+name, headers={'authorization':'Bearer '+token}, json={'arguments': arguments})


@pytest.mark.parametrize('fault', ['ceo', 'coo', 'human', 'client', 'disabled', 'bad-signature', 'expired', 'issuer', 'audience', 'extra-scope'])
def test_profile_auth_closure(rsa_key, tmp_path, fault):
    from integrations.mastermind_executive_app.inference import SERVICE_SCOPE
    app, token, current = setup_app(rsa_key, tmp_path)
    if fault == 'disabled': current['binding'] = None
    elif fault == 'bad-signature': token += 'invalid'
    else:
        claims = {'scope': SERVICE_SCOPE, 'sub': 'service-vps'}
        claims.update({'ceo': {'scope': 'mastermind.executive.read mastermind.executive.intent.submit'},
            'coo': {'scope': 'mastermind.executive.read mastermind.executive.coo.act'},
            'human': {'sub': auth.SUBJECT}, 'client': {'client_id':'other-client'},
            'expired': {'iat': auth.NOW-600, 'nbf': auth.NOW-600, 'exp': auth.NOW-60},
            'issuer': {'iss':'https://foreign.invalid'}, 'audience': {'aud':'https://foreign.invalid'},
            'extra-scope': {'scope':SERVICE_SCOPE+' mastermind.executive.coo.act'}}[fault])
        token = auth._token(rsa_key, **claims)
    result = asyncio.run(call(app, token, 'service_intent_status', {'operation_key':'inference-test'}))
    assert result.status_code in (401, 403)


@pytest.mark.parametrize('field', ['actor', 'provider', 'execution_profile', 'allowed_write_paths', 'validation', 'attempt_limit', 'grounding'])
def test_request_closed(field):
    from control_plane.executive_inference_contract import normalize_request
    with pytest.raises(ValueError):
        normalize_request(dict(operation_key='inference-test', objective='Research', **{field:'untrusted'}))


@pytest.mark.parametrize('outcome', ['lost', 'raised', 'cancelled', 'backend-error', 'malformed', 'not-sent'])
def test_submit_transport_uncertainty_never_replays(rsa_key, tmp_path, outcome):
    from integrations.mastermind_executive_app.gateway import CeoIngressResponse
    app, token, _ = setup_app(rsa_key, tmp_path)
    sent = []
    async def send(path, frame):
        sent.append(frame)
        if frame['schema'].endswith('grounding.v1'):
            return CeoIngressResponse('sent_ok', ok=True, result=GROUND)
        if outcome == 'raised': raise RuntimeError('PRIVATE_SECRET')
        if outcome == 'cancelled': raise asyncio.CancelledError()
        if outcome == 'backend-error': return CeoIngressResponse('sent_ok', ok=False, error={'code':'backend_refused','message':'PRIVATE_SECRET'})
        if outcome == 'malformed': return CeoIngressResponse('sent_ok', ok=True, result={'accepted':True})
        return CeoIngressResponse('not_sent' if outcome == 'not-sent' else 'sent_effect_unknown')
    app._client.send_frame = send
    result = asyncio.run(call(app, token, 'submit_service_intent', REQUEST))
    assert result.status_code == (503 if outcome == 'not-sent' else 202)
    assert result.json()['status'] == ('ingress_unavailable' if outcome == 'not-sent' else 'effect_unknown')
    assert 'PRIVATE_SECRET' not in result.text and len(sent) == 2


GROUND = {'mastermind_sha':'1'*40, 'macro_sha':'2'*40, 'boot_packet_schema':'mastermind.ceo_boot_packet.v1'}
REQUEST = {'operation_key':'inference-test', 'objective':'Summarize the supplied research.'}


def test_service_profile_contract_is_closed_without_shared_server_mount():
    from integrations.executive_mcp.inference import MCP_PATH, TOOL_SPECS
    assert MCP_PATH == "/mcp/service-inference"
    assert [tool.name for tool in TOOL_SPECS] == [
        "submit_service_intent", "service_intent_status", "executive_fabric"
    ]
    assert all(tool.name not in {"submit_ceo_intent", "submit_coo_ruling"} for tool in TOOL_SPECS)


def test_status_refuses_foreign_service_under_same_intent_id(tmp_path):
    from control_plane.executive_inference_contract import derive
    from control_plane.executive_inference_ingress import handle_frame, STATUS_SCHEMA
    from control_plane.executive_ceo_ingress import CeoIngressError
    rt = Runtime.at(tmp_path/'runtime')
    envelope = derive(REQUEST, GROUND)['envelope']
    envelope.update(actor='svc-site-maintenance', principal_id='svc-site-maintenance')
    ceo_intent.submit_intent(rt, envelope)
    with pytest.raises(CeoIngressError):
        asyncio.run(handle_frame(dict(schema=STATUS_SCHEMA, operation_key=REQUEST['operation_key']),
            runtime=rt, grounding_provider=None, workspace_root=tmp_path, admission_guard=None))


def test_app_result_is_bound_to_service_receipt_and_rechecks_auth(rsa_key, tmp_path):
    from control_plane.executive_inference_contract import derive
    from integrations.mastermind_executive_app.gateway import CeoIngressResponse
    from tests.test_fabric_inference_client import result
    app, token, current = setup_app(rsa_key, tmp_path)
    rt = Runtime.at(tmp_path/'runtime')
    envelope = derive(REQUEST, GROUND)['envelope']
    receipt = ceo_intent.submit_intent(
        rt, envelope, workspace_root=tmp_path,
        service_admission_guard=lambda _: None,
        service_execution_binding=host_execution_binding(tmp_path, envelope['intent_id']),
    )
    selection = dict(root_job_id=receipt['job_id'], job_id=receipt['job_id'],
                     attempt_id='ATT-'+'a'*32, result_envelope_digest='b'*64)
    reads = []
    async def send(path, frame):
        return CeoIngressResponse('sent_ok', ok=True, result={'receipt': receipt,
            'terminal_result_ref': dict(selection, orchestration_role='aggregation', validation='UNVALIDATED')})
    async def reader(name, args):
        reads.append(args)
        return result(selection)
    app._client.send_frame = send
    app._reader.call = reader
    async def run():
        # Edge-only fixture tests exact selection and scope; canonical content validation
        # is separately exercised against the actual retained Runtime projector.
        good = await call(app, token, 'executive_fabric', dict(selection, view='result', operation_key=REQUEST['operation_key']))
        assert good.status_code == 200, good.text
        bad = await call(app, token, 'executive_fabric', dict(selection, root_job_id='JOB-999', view='result', operation_key=REQUEST['operation_key']))
        assert bad.status_code == 403 and len(reads) == 1
        async def revoke(name, args):
            current['binding'] = None
            return result(selection)
        app._reader.call = revoke
        revoked = await call(app, token, 'executive_fabric', dict(selection, view='result', operation_key=REQUEST['operation_key']))
        assert revoked.status_code == 403 and 'data' not in revoked.json()
    asyncio.run(run())


def test_app_handler_fixture_loss_reconciliation_and_honest_null(rsa_key, tmp_path, monkeypatch):
    """Explicit in-process adapter fixture; no claim of installed host composition."""
    from control_plane.executive_inference_ingress import handle_frame, SUBMIT_SCHEMA
    from integrations.mastermind_executive_app.gateway import CeoIngressResponse
    app, token, _ = setup_app(rsa_key, tmp_path)
    rt = Runtime.at(tmp_path/'runtime')
    class Ground:
        def observe(self): return GROUND
    submits = []
    async def observe(*args): return GROUND
    monkeypatch.setattr('integrations.mastermind_executive_app.inference.observe_ingress_grounding', observe)
    async def send(path, frame):
        result = await handle_frame(
            frame, runtime=rt, grounding_provider=Ground(),
            workspace_root=tmp_path, admission_guard=lambda _: None,
            execution_binding_provider=lambda identity: host_execution_binding(tmp_path, identity),
        )
        if frame['schema'] == SUBMIT_SCHEMA:
            submits.append(frame)
            return CeoIngressResponse('sent_effect_unknown')
        return CeoIngressResponse('sent_ok', ok=True, result=result)
    app._client.send_frame = send
    async def no_reader(*args): pytest.fail('ordinary service Job has no Fabric reference')
    app._reader.call = no_reader
    async def run():
        lost = await call(app, token, 'submit_service_intent', REQUEST)
        assert lost.status_code == 202
        recovered = await call(app, token, 'service_intent_status', {'operation_key':REQUEST['operation_key']})
        assert recovered.status_code == 200
        assert recovered.json()['terminal_result_ref'] is None
        receipt = recovered.json()['receipt']
        job = rt.jobs.get_job(receipt['job_id'])
        assert job.orchestration_role is None
        assert rt.attempts.list_attempts(job.job_id) == []
        selection = dict(operation_key=REQUEST['operation_key'], view='result', root_job_id=job.job_id,
            job_id=job.job_id, attempt_id='ATT-'+'a'*32, result_envelope_digest='b'*64)
        unavailable = await call(app, token, 'executive_fabric', selection)
        assert unavailable.status_code == 503 and 'data' not in unavailable.json()
        assert len(rt.jobs.list_jobs()) == len(submits) == 1
    asyncio.run(run())


@pytest.mark.parametrize('guard', [None, False, lambda _: False, lambda _: True, lambda _: {}])
def test_fresh_sink_requires_synchronous_host_guard(tmp_path, guard):
    from control_plane.executive_inference_contract import derive
    rt = Runtime.at(tmp_path/'runtime')
    with pytest.raises(ceo_intent.CeoIntentError, match='trusted service admission refused'):
        ceo_intent.submit_intent(rt, derive(REQUEST, GROUND)['envelope'], service_admission_guard=guard)
    assert rt.jobs.list_jobs() == []


def test_sink_guard_is_last_synchronous_check_and_duplicate_skips_it(tmp_path, monkeypatch):
    from control_plane.executive_inference_contract import derive
    rt = Runtime.at(tmp_path/'runtime')
    envelope = derive(REQUEST, GROUND)['envelope']
    calls = []
    create = rt.jobs.create_job
    def guard(candidate):
        calls.append('guard')
        candidate['objective'] = 'must not mutate canonical intent'
    def checked_create(*args, **kwargs):
        assert calls == ['guard']
        calls.append('create')
        return create(*args, **kwargs)
    monkeypatch.setattr(rt.jobs, 'create_job', checked_create)
    first = ceo_intent.submit_intent(
        rt, envelope, workspace_root=tmp_path,
        service_admission_guard=guard,
        service_execution_binding=host_execution_binding(tmp_path, envelope['intent_id']),
    )
    def revoked(_): pytest.fail('accepted duplicate must not re-run guard')
    duplicate = ceo_intent.submit_intent(rt, envelope, service_admission_guard=revoked)
    assert duplicate['duplicate'] and first['job_id'] == duplicate['job_id']
    assert rt.jobs.get_job(first['job_id']).objective == REQUEST['objective']
    assert calls == ['guard', 'create']


def test_direct_emitter_cannot_bypass_sink_guard(tmp_path):
    rt = Runtime.at(tmp_path/'runtime')
    request = dict(REQUEST, department='executive-infrastructure', priority=3,
        execution_profile='research_only', attempt_limit=1, grounding=GROUND)
    with pytest.raises(ceo_intent.CeoIntentError):
        esp.submit(esp.service_principal('svc-vps-inference'), request, rt)
    assert rt.jobs.list_jobs() == []
    # The historic maintenance principal still needs no new host input.
    receipt = esp.submit(esp.service_principal('svc-site-maintenance'), request, rt)
    assert receipt['accepted']


def test_late_revocation_at_final_grounding_read_refuses_creation(tmp_path):
    from control_plane import executive_inference_ingress as service
    from control_plane.executive_ceo_ingress import CeoIngressError
    rt = Runtime.at(tmp_path/'runtime')
    armed = True
    calls = []
    class Ground:
        def observe(self):
            nonlocal armed
            calls.append('ground')
            if len(calls) == 2: armed = False
            return GROUND
    def guard(_):
        calls.append('guard')
        if not armed: raise ValueError('revoked')
    with pytest.raises(CeoIngressError):
        asyncio.run(service.handle_frame(dict(schema=service.SUBMIT_SCHEMA,
            request=REQUEST, observed_grounding=GROUND), runtime=rt,
            grounding_provider=Ground(), workspace_root=tmp_path, admission_guard=guard,
            execution_binding_provider=lambda identity: host_execution_binding(tmp_path, identity)))
    assert calls == ['ground', 'ground', 'guard']
    assert rt.jobs.list_jobs() == []


def test_async_and_raised_guards_refuse_without_job(tmp_path):
    from control_plane.executive_inference_contract import derive
    rt = Runtime.at(tmp_path/'runtime')
    async def async_guard(_): pytest.fail('async guard must not execute')
    def raised(_): raise RuntimeError('private guard failure')
    for guard in (async_guard, raised):
        with pytest.raises(ceo_intent.CeoIntentError):
            ceo_intent.submit_intent(rt, derive(REQUEST, GROUND)['envelope'], service_admission_guard=guard)
    assert rt.jobs.list_jobs() == []
