"""Canonical acquisition with real Runtime/Wake, guard and Relay owners.

Account grants, Workspace publication and Slack storage are explicit disposable
fixtures. No installed App request, enrollment or principal Wake is claimed.
"""
import asyncio
import copy
import dataclasses
from decimal import Decimal
import json
import traceback

import pytest

from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.coo_principal_mandate import NewEffectGate
from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation, PhysicalDialogueSourceIdentity,
    attention_source_ref, correlated_source_ref,
)
from control_plane.executive_dialogue_observation import (
    parse_observation_request, reduce_dialogue_observation, response_bytes,
)
from control_plane.wake_events import mint_obligation
from control_plane.wake_ledger import (
    AckMode, SourceReadHealth, TrustedAckContext, acknowledge, ack_record,
    expected_resolution_code, requested_record, resolve_source, resolved_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import CooPrincipalDialogueCaller
from integrations.slack_agent_dialogue.contract_v2 import build_message_v2, render_message_v2, render_parent_v2
from integrations.slack_agent_dialogue.engine import SlackMessage
from integrations.slack_agent_dialogue.executive_observation_client import ExecutiveDialogueObservationClient
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.principal_source_acquisition import (
    PrincipalSourceAcquisitionUnavailable, acquire_principal_decision_source,
)
from tests.test_executive_service import _strict_dialogue_runtime
from tests.test_principal_dialogue_authority_guard import prepared
from tests.test_executive_coo_host import mandate
from tests.test_slack_agent_dialogue_turn_watcher import _body
from tests import test_principal_source_reader as relay


@pytest.mark.parametrize("change", [
    "none", "foreign_work", "foreign_root", "generation", "profile", "revoked",
    "ceo_target", "missing", "resolved", "wrong_worker", "root_source_unavailable",
    "answered", "revoke_during_read", "resolve_during_read", "root_source_unavailable_during_read",
    "host_rule", "host_resolved", "host_revoked", "host_ack", "host_request_revoked", "host_request_during_read", "host_framed_rule", "host_app_receiver", "host_app_receiver_local",
    "host_recovery_resolved", "host_recovery_paused", "host_recovery_empty",
    "host_recovery_unknown", "host_recovery_work", "host_recovery_root",
    "host_recovery_principal", "host_recovery_generation", "host_recovery_mission",
    "host_recovery_before", "host_recovery_after", "host_recovery_async",
    "host_recovery_truthy", "host_recovery_missing", "host_recovery_duplicate",
])
def test_acquisition_derives_exact_inputs_and_refuses_drift(tmp_path, monkeypatch, change):
    fixture = _strict_dialogue_runtime(tmp_path, monkeypatch)
    runtime, parent = fixture.runtime, fixture.parent
    authority, config, _, _ = prepared(tmp_path, monkeypatch)
    config["missions"][0]["work_ref"] = parent["work_ref"]
    document = json.loads(json.dumps(mandate.mission_doc(work_ref=parent["work_ref"])).replace(
        '"JOB-100"', json.dumps(fixture.root.job_id)))
    monkeypatch.setattr(authority.workspace, "read_mission_for_work_ref", lambda _: copy.deepcopy(document))
    row, principal, authority_fact = authority.source.snapshot(parent["work_ref"])
    context = PrincipalAdmissionContext(row["work_ref"], principal.principal_binding_digest,
        authority_fact.mission_authority_ref, authority_fact.authority_generation_digest)
    caller = CooPrincipalDialogueCaller(context, fixture.root.job_id, "qualified-test",
        authority_fact.capability_profile_digest, NewEffectGate.OPEN, "coo", "coo")
    worker = {k: getattr(fixture.candidate, k) for k in ("job_id", "attempt_id", "worker_id")}
    message = build_message_v2({"schema": "mastermind.agent_dialogue.v2",
        "message_key": "asd-source-acquisition-request-001", "message_type": "DECISION_REQUEST",
        "work_ref": parent["work_ref"], "commission_ref": parent["commission_ref"],
        "session_ref": parent["session_ref"], "actor_ref": {"kind": "worker_attempt", **worker},
        "reply_to_message_key": None, "applies_to": {"kind": "executive_attempt", **worker},
        "summary": "Original ordinary decision.", "body": _body("DECISION_REQUEST"),
        "evidence_refs": [], "requires_response": True, "created_at": "2026-09-03T01:00:01Z"})
    candidate = fixture.candidate.to_dict()
    if change == "wrong_worker":
        candidate["worker_id"] = "worker-foreign"
    seat = "ceo" if change == "ceo_target" else "coo"
    logical = correlated_source_ref(attention_source_ref=attention_source_ref(
        parent_fingerprint=parent["fingerprint"], message_key=message["message_key"], target_seat=seat),
        parent_fingerprint=parent["fingerprint"], operation_key=parent["operation_key"], candidate=candidate)
    obligation = mint_obligation(wake_kind="dialogue_turn_pending", source_kind="agent_dialogue_attention",
        source_ref=logical, declared_target_seat=seat, job_id=candidate["job_id"],
        attempt_id=candidate["attempt_id"], root_job_id=caller.root_job_id,
        source_workstream=parent["work_ref"], emitted_at="2026-10-14T00:00:00Z")
    physical = PhysicalDialogueSourceIdentity.create(logical_source_ref=logical,
        obligation_id=obligation.obligation_id, observation=DialogueSourceObservation(
            relay.WORKSPACE, relay.CHANNEL, relay.THREAD, message["message_key"], message["fingerprint"]),
        parent_fingerprint=parent["fingerprint"], operation_key=parent["operation_key"],
        target_seat=seat, candidate=candidate)
    repository = WakeLedgerRepository(runtime)
    repository.append_record(requested_record(obligation, physical_source=physical), obligation=obligation)

    def resolve():
        ack = acknowledge(obligation, trusted=TrustedAckContext(ack_mode=AckMode.HUMAN_OPERATOR,
            target_seat="coo", session_alias="SYNTHETIC-OPERATOR", reasoning_surface="human",
            acknowledged_at="2026-10-14T00:00:01Z", operator_authority_receipt="OP-SOURCE-TEST"),
            claimed_obligation_ids=(obligation.obligation_id,))
        repository.append_record(ack_record(obligation, ack))
        resolution = resolve_source(obligation, code=expected_resolution_code(obligation),
            health=SourceReadHealth.HEALTHY, source_present=False,
            snapshot_digest="d" * 64, resolved_at="2026-10-14T00:00:02Z")
        repository.append_record(resolved_record(obligation, resolution))

    def remove_root_source():
        # Fault injection at the canonical owner's read boundary. Actual Runtime
        # Events are immutable; this does not claim they can be rewritten.
        import integrations.slack_agent_dialogue.principal_source_acquisition as acquisition
        def unavailable(*args, **kwargs):
            raise PermissionError("PRIVATE_CANARY /private/source")
        monkeypatch.setattr(acquisition, "_dialogue_source_from_root_creation", unavailable)

    oid = obligation.obligation_id
    if change == "foreign_work":
        caller = dataclasses.replace(caller, admission_context=dataclasses.replace(context, work_ref="WS:FOREIGN"))
    elif change == "foreign_root": caller = dataclasses.replace(caller, root_job_id="JOB-999")
    elif change == "generation":
        caller = dataclasses.replace(caller, admission_context=dataclasses.replace(context, authority_generation_digest="f" * 64))
    elif change == "profile": caller = dataclasses.replace(caller, capability_profile_digest="f" * 64)
    elif change == "revoked": config["missions"][0]["enabled"] = False
    elif change == "missing": oid = "wake-" + "0" * 32
    elif change == "resolved": resolve()
    elif change == "root_source_unavailable": remove_root_source()
    baseline = [runtime.events.list_events()]

    async def scenario():
        calls = []
        request_current = [True]
        async def observe(reader, writer):
            try:
                request = parse_observation_request(await reader.readline())
                calls.append(request.parent)
                facts = fixture.facts_reader._runtime_dialogue_observation_facts(runtime, request.parent)
                response = reduce_dialogue_observation(parent=request.parent, facts=facts, thread_ts=relay.THREAD)
                if change == "revoke_during_read": config["missions"][0]["enabled"] = False
                elif change == "resolve_during_read": resolve()
                elif change == "root_source_unavailable_during_read": remove_root_source()
                elif change == "host_request_during_read": request_current[0] = False
                baseline[0] = runtime.events.list_events()
                writer.write(response_bytes(response))
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        path = tmp_path / "observation.sock"
        server = await asyncio.start_unix_server(observe, path=str(path))
        slack = InMemorySlackClient(relay_bot_user_id=relay.BOT,
            next_timestamp=Decimal(relay.LATER_TS) + Decimal("0.000001"))
        slack.add_parent(SlackMessage(ts=relay.THREAD, author_user_id=relay.BOT, text=render_parent_v2(parent)))
        slack.add_reply(SlackMessage(ts=relay.PREDECESSOR_TS, author_user_id=relay.BOT,
            text=render_message_v2(message), thread_ts=relay.THREAD))
        if change == "answered":
            reply = build_message_v2({**{k: v for k, v in message.items() if k != "fingerprint"},
                "message_key": "asd-source-existing-ruling-001", "message_type": "RULING",
                "actor_ref": {"kind": "executive_surface", "seat": "ceo", "reasoning_surface": "chatgpt"},
                "body": _body("RULING"), "reply_to_message_key": message["message_key"],
                "requires_response": False})
            slack.add_reply(SlackMessage(ts=relay.LATER_TS, author_user_id=relay.BOT,
                text=render_message_v2(reply), thread_ts=relay.THREAD))
        relay_path = tmp_path / "relay.sock"
        service = await relay._start_relay(relay_path, slack)
        try:
            args = dict(runtime=runtime, authority=authority, caller=caller, obligation_id=oid,
                socket_path=relay_path, observation_client=ExecutiveDialogueObservationClient(path))
            if change == "host_app_receiver_local":
                from control_plane.executive_service import ExecutiveControlService
                from integrations.slack_agent_dialogue.host_local_observation import HostLocalDialogueObservationReader
                from tests.test_executive_ceo_ingress import _config
                owner = ExecutiveControlService(_config(tmp_path / "host", socket_root=tmp_path))
                owner.runtime = runtime
                owner._ceo_ingress_ready = True
                owner._service_state = "READY"
                facts_reader = owner._runtime_dialogue_observation_facts
                def counted_facts(current_runtime, current_parent):
                    assert current_runtime is runtime
                    calls.append(current_parent)
                    return facts_reader(current_runtime, current_parent)
                monkeypatch.setattr(owner, "_runtime_dialogue_observation_facts", counted_facts)
                async def no_observation_socket(*_, **__):
                    raise AssertionError("Control cannot impersonate the Relay observation peer")
                monkeypatch.setattr(ExecutiveDialogueObservationClient, "_exchange", no_observation_socket)
                args["observation_client"] = HostLocalDialogueObservationReader(owner, runtime)
            if change.startswith("host_"):
                from integrations.mastermind_company_principal_decision_host import build_acquired_principal_decision_host
                from integrations.mastermind_company_principal_runtime_fence import PRINCIPAL_RUNTIME_AGGREGATE_TYPE
                from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
                class DecisionPolicy:
                    def minimum_authority(self, *, request, option):
                        return "WITHIN_COMMISSION" if option["id"] == "opt-continue" else "CHAIRMAN_REQUIRED"
                    def allows_continuation(self, **_):
                        return False
                service.engine_v2.authority_policy = DecisionPolicy()
                def receiving_guard():
                    if not request_current[0]:
                        raise ValueError("request closed")
                framed = None
                if change == "host_framed_rule":
                    from integrations.company_dialogue_principal_app_contract import encode_app_request, decode_app_request
                    framed = decode_app_request(encode_app_request(caller=caller,
                        obligation_id=oid, tool="ruling",
                        arguments={k: v for k, v in _body("RULING").items() if k != "canonical_ref"}))
                    args.update(caller=framed.caller, obligation_id=framed.obligation_id)
                if change == "host_request_during_read":
                    with pytest.raises(ValueError, match="request closed"):
                        await build_acquired_principal_decision_host(**args,
                            receiving_request_guard=receiving_guard)
                    assert calls == [parent]
                    assert runtime.events.list_events() == baseline[0]
                    assert slack.post_call_count == slack.parent_post_call_count == 0
                    return
                receiver_result = None
                if change in {"host_app_receiver", "host_app_receiver_local"}:
                    from integrations import mastermind_company_principal_app_receiver as receiver
                    from integrations.company_dialogue_principal_app_contract import encode_app_request
                    captured = []
                    async def capture_host(**kwargs):
                        acquired_host = await build_acquired_principal_decision_host(**kwargs)
                        captured.append(acquired_host)
                        return acquired_host
                    monkeypatch.setattr(receiver, "build_acquired_principal_decision_host", capture_host)
                    provider = receiver.PrincipalDialogueAppReceiver(runtime, authority, relay_path,
                        args["observation_client"])
                    receiver_result = await provider.ruling(encode_app_request(caller=caller,
                        obligation_id=oid, tool="ruling",
                        arguments={k: v for k, v in _body("RULING").items() if k != "canonical_ref"}),
                        receiving_request_guard=receiving_guard)
                    assert len(captured) == 1
                    host = captured[0]
                else:
                    host = await build_acquired_principal_decision_host(**args,
                        receiving_request_guard=receiving_guard)
                    assert calls == [parent]
                if change == "host_recovery_empty":
                    before = runtime.events.list_events()
                    async def no_relay(*_, **__):
                        raise AssertionError("no COMMIT means no Relay read")
                    host.commit_owner.service_call = no_relay
                    assert await host.commit_owner.reconcile_obligation(obligation_id=oid,
                        context=context, root_job_id=caller.root_job_id,
                        receiving_read_guard=receiving_guard) is None
                    assert runtime.events.list_events() == before
                    assert slack.post_call_count == slack.parent_post_call_count == 0
                    return
                if change == "host_resolved": resolve()
                elif change == "host_revoked": config["missions"][0]["enabled"] = False
                elif change == "host_request_revoked": request_current[0] = False
                elif change == "host_ack":
                    ack = acknowledge(obligation, trusted=TrustedAckContext(ack_mode=AckMode.HUMAN_OPERATOR,
                        target_seat="coo", session_alias="SYNTHETIC-OPERATOR", reasoning_surface="human",
                        acknowledged_at="2026-10-14T00:00:01Z", operator_authority_receipt="OP-SOURCE-TEST"),
                        claimed_obligation_ids=(oid,))
                    repository.append_record(ack_record(obligation, ack))
                arguments = {k: v for k, v in _body("RULING").items() if k != "canonical_ref"}
                if framed is not None:
                    arguments = framed.arguments
                result = receiver_result if receiver_result is not None else await host.gateway.call("ruling", arguments)
                events = runtime.events.list_events(aggregate_type=PRINCIPAL_RUNTIME_AGGREGATE_TYPE)
                # Revocation is now rejected by the current receiving/principal
                # binding before a second source read or COMMIT is attempted.
                assert calls == ([parent] if change in {
                    "host_revoked", "host_request_revoked"
                } else [parent, parent])
                if change in {"host_rule", "host_ack", "host_framed_rule", "host_app_receiver", "host_app_receiver_local"} or change.startswith("host_recovery_"):
                    assert result["ok"] is True, result
                    assert len(events) == slack.post_call_count == 1
                    # The original worker consumes using its retained parent
                    # context. A completed App request cannot lend its expired
                    # foreground authority to this later worker read.
                    worker_context = DialogueContextV2(work_ref=parent["work_ref"],
                        commission_ref=parent["commission_ref"], session_ref=parent["session_ref"],
                        operation_key=parent["operation_key"], watch_mode=parent["watch_mode"],
                        actor_ref=message["actor_ref"], applies_to=message["applies_to"])
                    consumed = await service.engine_v2.wait_for_reply(thread_ts=relay.THREAD,
                        context=worker_context, request_message_key=message["message_key"],
                        expected_types=("RULING",), max_attempts=1)
                    assert consumed["reply"]["message_key"] == events[0].aggregate_id
                    assert consumed["authority"]["executable"] is True
                    await host.gateway.call("ruling", arguments)
                    assert slack.post_call_count == 1
                    if change.startswith("host_recovery_"):
                        from integrations.mastermind_company_principal_runtime_fence import (
                            PrincipalDialogueRuntimeCommitOwner, PrincipalRuntimeFenceError,
                        )
                        from integrations.slack_agent_dialogue.service import call_service
                        # Discard the response and host. A new owner has no live
                        # binding and must recover solely from original records.
                        result = None
                        class NoFreshBinding:
                            def resolve(self):
                                raise AssertionError("recovery must not reacquire a send binding")
                        def no_new_effect(**_):
                            raise AssertionError("recovery must not request new-effect authority")
                        operations = []
                        async def read_only_service(path, frame):
                            operations.append(frame["operation"])
                            assert frame["operation"] == "read_thread"
                            if change == "host_recovery_unknown":
                                return {"ok": False}
                            value = await call_service(path, frame)
                            if change == "host_recovery_after": request_current[0] = False
                            return value
                        owner = PrincipalDialogueRuntimeCommitOwner(runtime, NoFreshBinding(),
                            socket_path=relay_path, service_call=read_only_service,
                            principal_authority_guard=no_new_effect)
                        if change == "host_recovery_resolved": resolve()
                        if change == "host_recovery_paused": config["missions"][0]["enabled"] = False
                        recovery = dict(obligation_id=oid, context=context,
                            root_job_id=caller.root_job_id, receiving_read_guard=receiving_guard)
                        fields = {"work": ("work_ref", "WS:FOREIGN"),
                            "principal": ("principal_binding_digest", "0" * 64),
                            "generation": ("authority_generation_digest", "1" * 64),
                            "mission": ("mission_authority_ref", "authority:foreign")}
                        fault = change.removeprefix("host_recovery_")
                        if fault in fields:
                            key, value = fields[fault]
                            recovery["context"] = dataclasses.replace(context, **{key: value})
                        if fault == "root": recovery["root_job_id"] = "JOB-999"
                        if fault == "before": request_current[0] = False
                        if fault == "missing": recovery["receiving_read_guard"] = None
                        if fault == "truthy": recovery["receiving_read_guard"] = lambda: True
                        if fault == "async":
                            async def invalid_async():
                                raise AssertionError("must not await a permission guard")
                            recovery["receiving_read_guard"] = invalid_async
                        if fault == "duplicate":
                            original_list = runtime.events.list_events
                            def duplicate_list(**kwargs):
                                rows = original_list(**kwargs)
                                return rows + rows if kwargs.get("aggregate_type") == PRINCIPAL_RUNTIME_AGGREGATE_TYPE else rows
                            monkeypatch.setattr(runtime.events, "list_events", duplicate_list)
                        before = runtime.events.list_events()
                        if fault in {"resolved", "paused", "unknown"}:
                            recovered = await owner.reconcile_obligation(**recovery)
                            assert recovered.message_key == events[0].aggregate_id
                            assert recovered.event_id == events[0].event_id
                            assert recovered.state.value == ("EFFECT_UNKNOWN" if fault == "unknown" else "APPLIED")
                            assert operations == ["read_thread"]
                        else:
                            with pytest.raises(PrincipalRuntimeFenceError) as error:
                                await owner.reconcile_obligation(**recovery)
                            assert str(error.value) == "principal original reply unavailable"
                            assert error.value.__cause__ is None
                            assert operations == (["read_thread"] if fault == "after" else [])
                        assert runtime.events.list_events() == before
                        assert slack.post_call_count == 1
                else:
                    assert result["ok"] is False, result
                    assert result["error"]["code"] == ("BINDING_UNAVAILABLE" if change in {
                        "host_revoked", "host_request_revoked"
                    } else "EFFECT_FENCE_UNAVAILABLE")
                    assert events == [] and slack.post_call_count == 0
                assert slack.parent_post_call_count == 0
                return
            if change == "none":
                try:
                    result = await acquire_principal_decision_source(**args)
                except Exception as error:
                    chain = []
                    while error is not None:
                        chain.append((type(error).__name__, str(error), [(f.name, f.lineno) for f in traceback.extract_tb(error.__traceback__)]))
                        error = error.__context__
                    raise AssertionError(chain) from None
                assert result.decision_source.physical_source == physical
                derived = result.decision_source.context.normalized()
                assert {k: derived[k] for k in ("work_ref", "commission_ref", "watch_mode", "session_ref", "operation_key")} == {
                    k: parent[k] for k in ("work_ref", "commission_ref", "watch_mode", "session_ref", "operation_key")}
                assert result.current.binding.reply_to_message_key == message["message_key"]
                assert result.current.observation.candidate == fixture.candidate
                assert calls == [parent]
                with pytest.raises(TypeError): result.decision_source.context.actor_ref["seat"] = "ceo"
            else:
                with pytest.raises(PrincipalSourceAcquisitionUnavailable) as error:
                    await acquire_principal_decision_source(**args)
                assert str(error.value) == "PRINCIPAL_SOURCE_ACQUISITION_UNAVAILABLE"
                assert error.value.__cause__ is None
                if change not in {"answered", "revoke_during_read", "resolve_during_read", "root_source_unavailable_during_read"}:
                    assert calls == []
                else:
                    assert calls == [parent]
            assert slack.post_call_count == slack.parent_post_call_count == 0
            assert runtime.events.list_events() == baseline[0]
        finally:
            await service.close()
            server.close()
            await server.wait_closed()
    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["missing", "truthy", "async"])
def test_host_rejects_non_synchronous_request_guard_before_acquisition(monkeypatch, kind):
    import integrations.mastermind_company_principal_decision_host as composition
    async def forbidden(**_):
        raise AssertionError("source acquisition must not start")
    monkeypatch.setattr(composition, "acquire_principal_decision_source", forbidden)
    async def asynchronous():
        raise AssertionError("asynchronous authority must not execute")
    guard = {"missing": None, "truthy": lambda: True, "async": asynchronous}[kind]
    with pytest.raises(ValueError, match="receiving principal request unavailable"):
        asyncio.run(composition.build_acquired_principal_decision_host(
            runtime=None, authority=None, caller=None, obligation_id="not-used",
            socket_path=None, observation_client=None, receiving_request_guard=guard))
