"""Canonical acquisition with real Runtime/Wake, guard and Relay owners.

Account grants, Workspace publication and Slack storage are explicit disposable
fixtures. No installed App request, enrollment or principal Wake is claimed.
"""
import asyncio
import copy
import dataclasses
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
        async def observe(reader, writer):
            try:
                request = parse_observation_request(await reader.readline())
                calls.append(request.parent)
                facts = fixture.facts_reader._runtime_dialogue_observation_facts(runtime, request.parent)
                response = reduce_dialogue_observation(parent=request.parent, facts=facts, thread_ts=relay.THREAD)
                if change == "revoke_during_read": config["missions"][0]["enabled"] = False
                elif change == "resolve_during_read": resolve()
                elif change == "root_source_unavailable_during_read": remove_root_source()
                baseline[0] = runtime.events.list_events()
                writer.write(response_bytes(response))
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        path = tmp_path / "observation.sock"
        server = await asyncio.start_unix_server(observe, path=str(path))
        slack = InMemorySlackClient(relay_bot_user_id=relay.BOT)
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
