"""One local signed-App -> kernel peer -> Runtime -> original worker journey.

Enrollment, source publication and Slack storage are disposable fixtures. The
App, receiver, service handler, acquisition, COMMIT and consumption code is real.
The service lifecycle/installed producer is deliberately outside this proof.
"""
import asyncio
import dataclasses
import json
import os

import pytest

from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
from integrations.business_mcp_auth.contracts import AUTH_POLICY_SCHEMA
from integrations.company_dialogue_principal_app_contract import decode_app_request
from integrations.company_dialogue_principal_host_contract import MAX_REQUEST_BYTES
from integrations.mastermind_company_principal_app_receiver import PrincipalDialogueAppReceiver
from integrations.mastermind_executive_app.coo import create_coo_app
from integrations.mastermind_executive_app.coo_binding import _digest, principal_frame
from integrations.mastermind_executive_app.gateway import TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN
from integrations.mastermind_executive_app.principal_dialogue import forward_principal_ruling
from tests import test_principal_source_acquisition as source_case
from tests.test_executive_ceo_ingress import _config, _FakeGrounding, _FakeSupervisor
from tests.test_executive_principal_dialogue_forward import caller_fixture, fixture, rsa_key  # noqa: F401


@pytest.mark.parametrize("lose_response", [False, True])
@pytest.mark.parametrize("host_local", [False, True])
def test_signed_app_forward_to_original_worker(tmp_path, monkeypatch, rsa_key, lose_response, host_local):
    run_signed_app_journey(tmp_path, monkeypatch, rsa_key, lose_response, host_local)


@pytest.mark.parametrize("fault", ["stable", "read", "commit", "missing"])
def test_real_typed_qualification_stays_pinned_through_commit(tmp_path, monkeypatch, rsa_key, fault):
    run_signed_app_journey(tmp_path, monkeypatch, rsa_key, False, True, qualification_fault=fault)


def run_signed_app_journey(tmp_path, monkeypatch, rsa_key, lose_response, host_local, *, qualification_fault=None):
    _, token, app_current, settings = caller_fixture.setup(rsa_key, tmp_path)
    original_prepared = source_case.prepared
    selected = {}
    class ExpectedQualificationRefusal(Exception):
        pass
    original_start_relay = source_case.relay._start_relay
    async def capture_relay(path, slack):
        selected["slack"] = slack
        return await original_start_relay(path, slack)
    monkeypatch.setattr(source_case.relay, "_start_relay", capture_relay)

    def prepared(path, patcher):
        authority, config, document, args = original_prepared(path, patcher)
        # Both real auth owners observe one synthetic signed principal. Rebuild
        # the source generation from that binding; do not hand-stamp a caller.
        config["policy"] = {"schema": AUTH_POLICY_SCHEMA,
            **json.loads(json.dumps(dataclasses.asdict(settings.policy)))}
        config["binding"] = app_current["binding"]
        config["missions"][0]["principal_binding_digest"] = _digest(config["binding"]["binding"])
        selected.update(authority=authority, config=config)
        return authority, config, document, args
    monkeypatch.setattr(source_case, "prepared", prepared)

    original_ruling = PrincipalDialogueAppReceiver.ruling
    observed_frames = []

    async def through_app_and_service(provider, raw, *, receiving_request_guard):
        original = decode_app_request(raw)
        socket_path = tmp_path / "app.sock"
        guards, recorded_responses = [], []

        class Receiver:
            async def ruling(self, received, *, receiving_request_guard):
                actual = decode_app_request(received)
                observed_frames.append(actual)
                assert actual == original
                guards.append(receiving_request_guard)
                return await original_ruling(provider, received,
                    receiving_request_guard=receiving_request_guard)

        service = ExecutiveControlService(_config(tmp_path / "service", socket_root=tmp_path),
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=socket_path, ceo_ingress_peer_uid=os.geteuid()+1000,
            ceo_ingress_grounding_provider=_FakeGrounding(), ceo_ingress_armed=False,
            ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(), armed=False, grounding_provider=_FakeGrounding(),
                principal_admission_armed=True, principal_admission_guard=lambda envelope: None,
                principal_dialogue_provider_factory=lambda runtime: Receiver()))
        # Retain the scenario's actual Runtime. This fixture selects local
        # lifecycle state; it does not run or attest the installed launcher.
        service.runtime = provider.runtime
        if host_local:
            from integrations.slack_agent_dialogue.host_local_observation import HostLocalDialogueObservationReader
            # Preserve the scenario's read counter, but bind the reader to the
            # very service receiving the App request and its exact Runtime.
            service._runtime_dialogue_observation_facts = provider.observation_client.service._runtime_dialogue_observation_facts
            provider = dataclasses.replace(provider,
                observation_client=HostLocalDialogueObservationReader(service, provider.runtime))
            assert provider.observation_client.service is service
        if qualification_fault:
            from control_plane import foreground_operation as foreground
            from tests.test_foreground_operation import frame
            from tests.test_attended_qualification import selected as placement
            f = frame()
            item = placement(f)
            service.config = dataclasses.replace(service.config, coo_foreground_only=True,
                coo_autonomy_armed=True, coo_attended_work_placements=(item,))
            def change_qualification():
                changed = dataclasses.replace(item.qualification, arguments_sha256="0" * 64)
                service.config = dataclasses.replace(service.config, coo_attended_work_placements=(
                    dataclasses.replace(item, qualification=changed),))
            if qualification_fault == "read":
                original_resolve = HostLocalDialogueObservationReader.resolve
                async def changed_after_read(reader, **kwargs):
                    result = await original_resolve(reader, **kwargs)
                    change_qualification()
                    return result
                monkeypatch.setattr(HostLocalDialogueObservationReader, "resolve", changed_after_read)
            elif qualification_fault == "commit":
                from integrations.mastermind_company_principal_runtime_fence import PrincipalDialogueRuntimeCommitOwner
                original_commit = PrincipalDialogueRuntimeCommitOwner.before_commit
                def changed_in_commit(owner, intent, **kwargs):
                    original_guard = owner.principal_authority_guard
                    def inside_transaction(**guard_kwargs):
                        selected["commit_guard_reached"] = True
                        change_qualification()
                        return original_guard(**guard_kwargs)
                    owner.principal_authority_guard = inside_transaction
                    return original_commit(owner, intent, **kwargs)
                monkeypatch.setattr(PrincipalDialogueRuntimeCommitOwner, "before_commit", changed_in_commit)
        service._coo_execution_binding = service._load_coo_execution_binding()
        service._ceo_ingress_ready = True
        service._service_state = "READY"
        if lose_response:
            async def lose_wire_response(writer, payload, **kwargs):
                recorded_responses.append(payload)
                # Actual socket closes without any response bytes. A successful
                # COMMIT is not visible to the App and must never be re-sent.
            monkeypatch.setattr(service, "_send_ceo_ingress_response", lose_wire_response)
        async def receiving_handler(reader, writer):
            if qualification_fault and qualification_fault != "missing":
                # Explicit source fixture for the existing private foreground
                # owner; production App ingress does not manufacture it.
                async with foreground._session_bridge_foreground_dispatch(provider.runtime, f, lambda: None):
                    assert service._require_attended_qualification() == item.qualification
                    await service._handle_ceo_ingress_connection(reader, writer)
            else:
                await service._handle_ceo_ingress_connection(reader, writer)
        server = await asyncio.start_unix_server(receiving_handler,
            path=str(socket_path), limit=MAX_REQUEST_BYTES+1)
        authority, config = selected["authority"], selected["config"]
        current_settings = dataclasses.replace(settings,
            executive=dataclasses.replace(settings.executive, ceo_ingress_socket_path=socket_path),
            load_binding=lambda: config["binding"],
            authority_provider=lambda principal, work: authority.source.for_principal(principal_frame(principal), work)[2],
            mission_provider=lambda principal, work: authority.workspace.read_mission_for_work_ref(work))
        app = create_coo_app(current_settings, audit_sink=fixture.Sink())
        before = provider.runtime.events.list_events()
        try:
            outcome = await forward_principal_ruling(app, caller_fixture.request(token),
                work_ref=original.caller.admission_context.work_ref,
                obligation_id=original.obligation_id, arguments=original.arguments,
                reasoning_surface=original.caller.reasoning_surface)
            if qualification_fault in {"read", "commit", "missing"}:
                assert outcome.transport == TRANSPORT_SENT_UNKNOWN, outcome
                assert outcome.result is None
                assert provider.runtime.events.list_events() == before
                assert selected["slack"].post_call_count == selected["slack"].parent_post_call_count == 0
                assert bool(selected.get("commit_guard_reached")) is (qualification_fault == "commit")
                raise ExpectedQualificationRefusal()
            assert outcome.transport == (TRANSPORT_SENT_UNKNOWN if lose_response else TRANSPORT_SENT_OK), outcome
            assert outcome.obligation_id == original.obligation_id
            if lose_response:
                assert outcome.result is None and len(recorded_responses) == 1
                from integrations.mastermind_company_principal_runtime_fence import PrincipalDialogueRuntimeCommitOwner
                class NoFreshBinding:
                    def resolve(self): raise AssertionError("recovery must not reacquire a send binding")
                def no_new_effect(**kwargs): raise AssertionError("recovery is read only")
                before = provider.runtime.events.list_events()
                owner = PrincipalDialogueRuntimeCommitOwner(provider.runtime, NoFreshBinding(),
                    socket_path=provider.socket_path, principal_authority_guard=no_new_effect)
                observed = await owner.reconcile_obligation(obligation_id=outcome.obligation_id,
                    context=original.caller.admission_context, root_job_id=original.caller.root_job_id,
                    receiving_read_guard=guards[0])
                assert observed.state.value == "APPLIED"
                assert provider.runtime.events.list_events() == before
                # Only the enclosing test fixture consumes the recorded backend
                # result. The actual App received UNKNOWN with no result.
                return recorded_responses[0]["result"]
            return outcome.result
        finally:
            server.close()
            await server.wait_closed()
            pending = tuple(service._ceo_ingress_tasks)
            if pending: await asyncio.gather(*pending)
            if qualification_fault == "stable":
                with pytest.raises(foreground.ForegroundOperationClosed):
                    guards[0]()

    monkeypatch.setattr(PrincipalDialogueAppReceiver, "ruling", through_app_and_service)
    # Reuse the canonical source/Relay scenario and its one-COMMIT, one-post,
    # original-worker executable consumption and no-duplicate-effect assertions.
    def exercise():
        source_case.test_acquisition_derives_exact_inputs_and_refuses_drift(
            tmp_path, monkeypatch, "host_app_receiver_local" if host_local else "host_app_receiver")
    if qualification_fault in {"read", "commit", "missing"}:
        with pytest.raises(ExpectedQualificationRefusal): exercise()
    else:
        exercise()
    assert len(observed_frames) == (0 if qualification_fault == "missing" else 1)
