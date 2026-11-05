"""Signed App HTTP -> actual Unix peer -> canonical Runtime admission.

Host grounding/arm and the physical driver are explicit inert fixtures. The
public/inner bearer checks, request lifetime, private frame, root commit,
fresh-only observer, duplicate handling and retained status use actual code.
No provider, installed source, enrollment or production effect is exercised.
"""
import asyncio
import dataclasses
import json
import time
from pathlib import Path

import pytest

from control_plane import ceo_intent, executive_ceo_ingress as ingress
from control_plane.executive_service import _ForegroundExecution, _canonical_json
from integrations.executive_mcp import server
from integrations.mastermind_executive_app.gateway import CeoIngressClient
from integrations.mastermind_executive_app.admission import reconcile_by_request_ref
from integrations.session_bridge.installed import InstalledSessionBridgeClient
from tests import test_mastermind_os_executive_transport as web
from tests import test_foreground_fresh_admission as fresh
from tests.test_executive_mcp_installed_fabric_composition import factory_service
from tests.test_foreground_operation import frame

rsa_key = web.rsa_key
short_socket_root = web.short_socket_root
settings = web.settings


def app_for(settings, *, boundary=None):
    owner = InstalledSessionBridgeClient(settings.ceo_ingress_socket_path, client=boundary)
    return server.build_web_ceo_v3_mcp_app(settings, audit_sink=web.Sink(),
        mdm_reader=web.FixedMdm(), session_target_projector=owner.targets,
        session_reply_handler=owner.send, session_summon_handler=owner.summon,
        os_session_bridge_client=owner, os_app=web._assets(),
        enable_os_executive_transport=True,
        os_executive_resource=settings.policies.submit.resource)


async def post(app, token, arguments, *, entered=None, disconnect=False):
    path = "/os/executive/submit"
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "scheme": "https", "method": "POST", "path": path,
        "raw_path": path.encode(), "root_path": "", "query_string": b"",
        "headers": [(b"host", b"mcp.mastermind-x.com"),
                    (b"content-type", b"application/json"),
                    (b"authorization", ("Bearer " + token).encode())],
        "client": ("127.0.0.1", 39999), "server": ("mcp.mastermind-x.com", 443)}
    frames, output = asyncio.Queue(), []
    await frames.put({"type": "http.request", "body": json.dumps({"arguments": arguments}).encode(),
                      "more_body": False})
    async def receive():
        return await frames.get()
    async def send(value):
        output.append(value)
    task = asyncio.create_task(app(scope, receive, send))
    if entered is not None:
        await asyncio.wait_for(entered.wait(), 3)
        if disconnect:
            await frames.put({"type": "http.disconnect"})
    await asyncio.wait_for(task, 5)
    status = next(item["status"] for item in output if item["type"] == "http.response.start")
    body = b"".join(item.get("body", b"") for item in output if item["type"] == "http.response.body")
    return status, json.loads(body)


@pytest.mark.parametrize("edge", ["success", "duplicate", "disconnect", "lost_result", "inner_denied", "read_only"])
def test_app_research_owns_original_foreground_admission(
        tmp_path, short_socket_root, monkeypatch, settings, rsa_key, edge):
    async def run():
        async with factory_service(tmp_path, short_socket_root, monkeypatch,
                profile="web_ceo_v3") as (service, raw, _):
            await service.start()
            runtime = service._require_runtime()
            fresh.phase1fc._register_placement_union(runtime)
            snapshot = _ForegroundExecution("ORDINARY_OPERATOR", _canonical_json(service._require_current_coo_binding()))
            monkeypatch.setattr(service, "_foreground_execution_state", lambda **kw: snapshot)
            monkeypatch.setattr(service, "_require_foreground_execution", lambda value:
                None if value == snapshot else pytest.fail("foreign host snapshot"))
            original_observe, original_submit = ingress._observe_trusted_grounding, ingress.handle_frame
            async def observed(_):
                return await original_observe(fresh.hooks.pr_a._FakeGrounding())
            async def submit(parsed, **kw):
                return await original_submit(parsed, runtime=runtime,
                    grounding_provider=fresh.hooks.pr_a._FakeGrounding(),
                    workspace_root=Path(raw["proof_workspace_root"]), service_state="READY",
                    ceo_ingress_armed=True, strict_v2_admission=True,
                    execution_binding_provider=lambda:
                        (kw["execution_binding_provider"](), fresh.phase1fc._v3_execution_binding())[1],
                    dialogue_source_provider=lambda *_: fresh.hooks._dialogue_source(),
                    admission_guard=kw["admission_guard"],
                    fresh_admission_observer=kw.get("fresh_admission_observer"))
            monkeypatch.setattr(ingress, "_observe_trusted_grounding", observed)
            monkeypatch.setattr(ingress, "handle_frame", submit)
            entered, closed = asyncio.Event(), asyncio.Event()
            drives = []
            async def drive(operation, root):
                operation.require_root(root)
                assert service._foreground_cycle_owner == (asyncio.current_task(), operation)
                drives.append(root)
                entered.set()
                if edge == "disconnect":
                    await operation.wait_closed()
                    closed.set()
                    operation.require_root(root)
                if edge == "lost_result":
                    raise RuntimeError("inert post-commit result loss")
                return {"state": "NO_ACTION", "root_job_id": root, "delivery": "INCOMPLETE"}
            monkeypatch.setattr(service, "_drive_foreground_cycle", drive)
            now = int(time.time())
            configured = dataclasses.replace(settings, clock=lambda: now,
                ceo_ingress_socket_path=Path(raw["ceo_ingress_socket_path"]))
            app = app_for(configured)
            seen_bearers = []
            actual_inner = app.os_transport._inner_app
            async def inner(scope, receive, send):
                seen_bearers.extend(value for key, value in scope["headers"] if key == b"authorization")
                if edge == "inner_denied":
                    scope["headers"] = [(key, value) for key, value in scope["headers"] if key != b"authorization"]
                await actual_inner(scope, receive, send)
            app.os_transport._inner_app = inner
            token_fn = web.fixture._read_token if edge == "read_only" else web.fixture._submit_token
            token = token_fn(rsa_key, iat=now-1, nbf=now-1, exp=now+120)
            arguments = frame("app-foreground-single-root")["arguments"]
            status, result = await post(app, token, arguments,
                entered=entered if edge == "disconnect" else None, disconnect=edge == "disconnect")
            if edge in {"inner_denied", "read_only"}:
                assert runtime.jobs.list_jobs() == [] and drives == []
                assert status == (202 if edge == "inner_denied" else 401)
            else:
                roots = [job for job in runtime.jobs.list_jobs() if job.parent_job_id is None]
                assert len(roots) == 1 and drives == [roots[0].job_id]
                if edge in {"disconnect", "lost_result"}:
                    assert status == 202 and result["status"] == "effect_unknown"
                else:
                    assert status == 200 and result["status"] == "accepted", result
                    receipt = result["receipt"]
                    assert receipt["job_id"] == roots[0].job_id and receipt["dispatched"] is False
                    assert "foreground_completion" not in receipt
                    retained = ceo_intent.resolve_intent(runtime, receipt["intent_id"])
                    assert retained["job_id"] == receipt["job_id"]
                if edge == "duplicate":
                    again_status, again = await post(app, token, arguments)
                    assert again_status == 200 and again["receipt"]["duplicate"] is True
                    assert again["receipt"]["job_id"] == roots[0].job_id
                    assert drives == [roots[0].job_id] and len(runtime.jobs.list_jobs()) == 1
                if edge in {"disconnect", "lost_result"}:
                    if edge == "disconnect":
                        await asyncio.wait_for(closed.wait(), 1)
                    recovered = await reconcile_by_request_ref(CeoIngressClient(),
                        socket_path=raw["ceo_ingress_socket_path"], request_ref=result["request_ref"])
                    assert recovered.status == "accepted" and recovered.receipt["job_id"] == roots[0].job_id
                    assert len(runtime.jobs.list_jobs()) == 1 and drives == [roots[0].job_id]
            if edge != "read_only":
                assert seen_bearers == [("Bearer " + token).encode()] * (2 if edge == "duplicate" else 1)
            assert runtime.attempts.list_attempts() == []
    asyncio.run(run())


@pytest.mark.parametrize("edge", ["success", "duplicate", "disconnect", "expiry", "inner_denied", "read_only"])
def test_source_composed_app_plan_only_retains_real_runtime_result(
        tmp_path, monkeypatch, settings, rsa_key, edge):
    """Socket-free framing fixture, real auth/source/Runtime/plan collector.

    This is not kernel-peer proof; the real-socket test above owns that check.
    """
    from common.session_bridge_private_contract import private_result
    from control_plane import foreground_operation as operation_scope
    from control_plane.executive_coo_cycle import CooCycle
    from control_plane.executive_runtime import JobStatus
    from integrations.mastermind_executive_app.gateway import CeoIngressResponse, TRANSPORT_SENT_OK
    from integrations.mastermind_executive_app import admission
    from integrations.session_bridge import http_foreground
    from tests.test_foreground_operation import admit
    from tests.test_foreground_operator_completion import service_at
    from tests import test_executive_os_phase1fc as roles

    async def run():
        service = service_at(tmp_path)
        runtime = service.runtime
        monkeypatch.setattr(service, "_foreground_execution_state",
            lambda **kw: _ForegroundExecution("ORDINARY_OPERATOR", b"{}"))
        monkeypatch.setattr(service, "_coo_binding_for_root",
            lambda _: {"operator_execution_profile_id": "ordinary", "operator_harness_armed": True})
        entered = asyncio.Event()
        seen, completions, unattended = [], [], []
        now = [int(time.time())]
        async def finish(dispatched):
            await asyncio.sleep(0)
            job = runtime.jobs.get_job(dispatched.job_id)
            assert job.orchestration_role == "plan"
            plan = {"schema_version": "mastermind.execution_plan/v1", "root_job_id": job.root_job_id,
                "plan_attempt_id": dispatched.attempt.attempt_id, "steps": [{
                "ordinal": 0, "step_id": "one", "objective": "Read one retained fact",
                "business_impact": "routine", "review_required": False,
                "requested_authorities": ["READ"], "allowed_write_paths": [],
                "validation_ids": [], "attempt_limit": 1, "cost_class": "small"}]}
            roles._complete_ohf_role(runtime, dispatched, plan, identity_seed=8300)
            service._dispatch_tasks.pop(job.job_id)
        def dispatch(job_id, command):
            value = runtime.attempts.dispatch_cycle_job(job_id, command_id=command, worker_id="worker-a")
            service._dispatch_tasks[job_id] = asyncio.create_task(finish(value))
            return value
        cycle = CooCycle(runtime, dispatcher=dispatch)
        async def once(root):
            return cycle.run_once(root)
        monkeypatch.setattr(service, "_run_coo_cycle", once)

        # Keep the pre-fix admission-only path executable in this fixture, so
        # the regression is a queued root without its owner, not a failed
        # network connection. Current source must never select this fallback.
        async def legacy_grounding(*_):
            return await ingress._observe_trusted_grounding(fresh.hooks.pr_a._FakeGrounding())
        async def legacy_send(_client, _path, framed):
            unattended.append(framed)
            result = await fresh.strict_call(runtime, tmp_path, observer=None, frame=framed)
            return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result=result)
        monkeypatch.setattr(admission, "observe_ingress_grounding", legacy_grounding)
        monkeypatch.setattr(CeoIngressClient, "send_frame", legacy_send)

        class LocalFramingFixture:
            async def send_frame(self, *args):
                pytest.fail("App research fell back to unattended transport")
            async def send_foreground_frame(self, path, framed):
                source = http_foreground.current_request()
                seen.append(framed)
                async with operation_scope._session_bridge_foreground_dispatch(
                        runtime, framed, source.require_live) as operation:
                    async with service._foreground_cycle_scope(operation):
                        receipt = await admit(runtime, tmp_path, operation, framed)
                        entered.set()
                        if edge == "disconnect":
                            await asyncio.Event().wait()
                        if edge == "expiry":
                            now[0] += 121
                            source.require_live()
                        if not receipt["duplicate"]:
                            completion = await service._drive_foreground_cycle(operation, receipt["job_id"])
                            completions.append(completion)
                            receipt = {**receipt, "foreground_completion": completion}
                        return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True,
                            result=private_result("session_summon", data=receipt))
        app = app_for(dataclasses.replace(settings, clock=lambda: now[0]), boundary=LocalFramingFixture())
        if edge == "inner_denied":
            actual_inner = app.os_transport._inner_app
            async def denied(scope, receive, send):
                scope["headers"] = [(key, value) for key, value in scope["headers"] if key != b"authorization"]
                await actual_inner(scope, receive, send)
            app.os_transport._inner_app = denied
        token_fn = web.fixture._read_token if edge == "read_only" else web.fixture._submit_token
        token = token_fn(rsa_key, iat=now[0]-1, nbf=now[0]-1, exp=now[0]+120)
        arguments = frame("app-source-plan-only")["arguments"]
        code, result = await post(app, token, arguments,
            entered=entered if edge == "disconnect" else None, disconnect=edge == "disconnect")
        if edge in {"inner_denied", "read_only"}:
            assert runtime.jobs.list_jobs() == [] and seen == []
        else:
            roots = [job for job in runtime.jobs.list_jobs() if job.parent_job_id is None]
            assert len(roots) == 1 and roots[0].status is JobStatus.QUEUED, (code, result, len(seen))
            assert seen and not unattended, "App admitted the root without its foreground execution owner"
            assert seen[0]["arguments"] == {
                **arguments, "allowed_write_paths": [], "attempt_limit": 2, "validation": {}}
            if edge in {"disconnect", "expiry"}:
                assert code == 202 and result["status"] == "effect_unknown"
                assert len(runtime.jobs.list_jobs()) == 1 and runtime.attempts.list_attempts() == []
            else:
                assert code == 200 and result["status"] == "accepted", result
                assert result["receipt"]["job_id"] == roots[0].job_id
                assert "foreground_completion" not in result["receipt"]
                assert completions[0]["state"] == "OPERATOR_COMPLETED"
                assert completions[0]["delivery"] == "INCOMPLETE"
                planner = next(job for job in runtime.jobs.list_jobs() if job.parent_job_id == roots[0].job_id)
                assert planner.status is JobStatus.COMPLETED
                runtime.validated_role_completion(planner.job_id, expected_attempt_id=planner.current_attempt_id)
                assert not [event for event in runtime.events.list_events(job_id=roots[0].job_id)
                            if event.event_type == "COO_PLAN_ADMITTED"]
                if edge == "duplicate":
                    _, duplicate = await post(app, token, arguments)
                    assert duplicate["receipt"]["duplicate"] is True
                    assert duplicate["receipt"]["job_id"] == roots[0].job_id
                    assert len(completions) == 1 and len(runtime.attempts.list_attempts()) == 1
        assert service._foreground_cycle_owner is None and not service._coo_action_tasks
    asyncio.run(run())
