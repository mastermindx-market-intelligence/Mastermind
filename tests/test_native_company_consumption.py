"""Runtime/Relay consumption composition with a fake provider boundary, not live proof."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile

import pytest

from control_plane.consultation_runtime import ConsultationRuntime
from control_plane.executive_runtime import StateConflict
from control_plane.operator_harness_contract import AttentionCompanyReadProjection
from control_plane.session_targets import route_obligation
from control_plane.wake_dispatcher import (
    TransportOutcome, TransportReceipt, WakeTransportCompletion, dispatch_persisted_nudge,
)
from control_plane.wake_ledger import LedgerPhase
from control_plane.wake_persist import WakeLedgerRepository
from integrations.company_consultation_dispatch import ConsultationRefusal
from tests import test_company_inbox_iac1 as fixtures
from tests.test_company_consultation_host import composed, call
from tests.test_company_consultation_targeted_dispatch import _bindings, _dispatch
from tests.test_executive_wake_persisted_dispatch import _POLICY, _codex_registry
from tests.test_native_company_receipt import (
    call as native_read, make_item, make_params, result_for,
)


@pytest.mark.parametrize("mode", ["success", "wake_advanced", "answer_digest", "process", "mcp_tx", "absent"])
def test_stored_native_consumer_uses_exact_answer_and_current_runtime_transaction(
    composed, monkeypatch, mode,
):
    async def scenario():
        with tempfile.TemporaryDirectory(prefix="c-native-", dir="/tmp") as directory:
            socket = Path(directory) / "r.sock"
            service, task = await fixtures._start_relay_service(
                socket_path=socket, client=composed.client,
            )
            host = composed.build_host(socket)
            provider_calls = []
            capability_transactions = []
            try:
                peers = await call(host, composed.a[1], "company.peers", {})
                args = fixtures._consult_args(
                    question="Native requester read.", evidence_refs=[],
                    artifact_revisions=[composed.revision],
                )
                args["to"] = peers["data"]["peers"][0]["peer_ref"]
                question = await call(host, composed.a[1], "company.consult", args)
                assert question["ok"], question
                ref = question["data"]["consultation_ref"]
                fixtures._deliver_and_ack_wake_path(composed.runtime, ref)
                answer = await call(host, composed.b[1], "company.reply", {
                    "consultation_ref": ref, "answer": "An exact bounded answer.",
                    "evidence_refs": [],
                })
                assert answer["ok"], answer
                returned = await call(host, composed.a[1], "company.consultation",
                                      {"consultation_ref": ref})
                assert returned["ok"] and returned["data"]["body_status"] == "AVAILABLE"
                dispatcher = _dispatch(composed, _bindings(composed), socket)
                frame = await dispatcher.packets.get_answer(ref)
                owner = ConsultationRuntime(
                    composed.runtime, repository_root=composed.repo,
                    _clock=lambda: "2026-09-14T00:00:00Z",
                )
                projection = owner.requester_answer_attention_replay(
                    frame, requester_attempt_id=composed.a[1],
                )
                binding = projection.binding
                native = native_read(make_params(
                    thread_id=binding.native_handle, turn_id="turn-native-consumer",
                    item=make_item(arguments={"consultation_ref": ref}, result=result_for(returned)),
                ), thread=binding.native_handle, turn="turn-native-consumer")
                assert native is not None
                facts = host._capability(composed.a[1])
                def mcp_binding(self, attempt_id, *, connection=None, **kwargs):
                    assert connection is not None and connection.in_transaction
                    capability_transactions.append(attempt_id)
                    if mode == "mcp_tx":
                        raise StateConflict("MCP currentness failed inside consumption transaction")
                    return host._capability(attempt_id, connection=connection)
                monkeypatch.setattr(
                    type(composed.runtime), "current_harness_mcp_binding_for_attempt", mcp_binding,
                )
                registry = replace(
                    _codex_registry(), targets={projection.target.session_alias: projection.target},
                    default_alias_by_seat={projection.target.target_seat: projection.target.session_alias},
                    workstream_alias_by_seat={}, root_job_bindings={
                        projection.obligation.root_job_id: {
                            projection.target.target_seat: projection.target.session_alias}},
                )
                route = route_obligation(projection.obligation, registry, binding=binding)
                repo = WakeLedgerRepository(composed.runtime)
                # Actual production reply stops at WAKE_REQUESTED in this slice.
                before = repo.list_records(projection.obligation.obligation_id)
                assert [row.record.phase for row in before] == [LedgerPhase.WAKE_REQUESTED]
                class Provider:
                    transport_id = "codex-app-server"
                    async def nudge(self, wake):
                        provider_calls.append(wake.nudge_id)
                        evidence = AttentionCompanyReadProjection(
                            target_attempt_id=composed.a[1],
                            process_generation_id=(
                                "stale-generation" if mode == "process"
                                else facts.binding.process_generation_id),
                            binding_id=binding.binding_id,
                            binding_generation=binding.binding_generation,
                            provider_session_id=binding.native_handle,
                            provider_native_turn_id="turn-native-consumer",
                            nudge_id=wake.nudge_id, consultation_ref=ref,
                            result_sha256=native["result_sha256"],
                            native_item_sha256=native["native_item_sha256"],
                            answer_attestation_sha256=(
                                "f" * 64 if mode == "answer_digest"
                                else native["answer_attestation_sha256"]),
                        )
                        return WakeTransportCompletion(
                            receipt=TransportReceipt(
                                outcome=TransportOutcome.DELIVERED, reason_code="delivered",
                                created_at="2026-09-14T00:00:00Z",
                                details=(("nudge_id", wake.nudge_id),),
                            ), company_read_projection=evidence,
                        )
                delivered = await dispatch_persisted_nudge(
                    repo, [(projection.obligation, route)], dispatcher=Provider(),
                    binding=binding, retry_policy=_POLICY,
                )
                assert delivered.native_company_read is not None
                record = repo.list_records(projection.obligation.obligation_id)[-1].record
                command = record.command_id if mode != "absent" else record.command_id + "-absent"
                before_consume = fixtures._consultation_event_count(
                    composed.runtime, ref, "CONSUMED_BY_REQUESTER",
                )
                assert before_consume == 0
                if mode == "wake_advanced":
                    from control_plane.wake_ledger import (
                        SourceReadHealth, SourceResolutionCode, resolve_source, resolved_record,
                    )
                    question_oid = fixtures._obligation_id_for_intent(composed.runtime, ref)
                    question_wake = next(row.obligation for row in repo.list_records(question_oid)
                                         if row.obligation is not None)
                    resolution = resolve_source(
                        question_wake, code=SourceResolutionCode.DIALOGUE_ATTENTION_ABSENT,
                        health=SourceReadHealth.HEALTHY, source_present=False,
                        snapshot_digest="f" * 64, resolved_at="2026-09-14T00:00:00Z",
                    )
                    repo.append_record(resolved_record(question_wake, resolution),
                                       obligation=question_wake)
                if mode not in {"success", "wake_advanced"}:
                    with pytest.raises((ConsultationRefusal, StateConflict)):
                        await host.consume_stored_native_read(command)
                    assert fixtures._consultation_event_count(
                        composed.runtime, ref, "CONSUMED_BY_REQUESTER") == 0
                    return
                result = await host.consume_stored_native_read(command)
                assert result == {"consultation_ref": ref, "state": "CONSUMED", "inserted": True}
                replay = await host.consume_stored_native_read(command)
                assert replay["inserted"] is False
                consumed = [event for event in composed.runtime.events.list_events(
                    aggregate_type="consultation", aggregate_id=ref)
                    if event.event_type == "CONSUMED_BY_REQUESTER"]
                assert len(consumed) == 1
                assert consumed[0].payload["native_delivery"] == {
                    "delivered_command_id": command,
                    "evidence": delivered.native_company_read.to_dict(),
                }
                assert len(capability_transactions) == 2
                assert len(provider_calls) == 1
                phases = [row.record.phase for row in repo.list_records(projection.obligation.obligation_id)]
                assert phases == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT,
                                  LedgerPhase.DELIVERED]
            finally:
                await fixtures._stop_relay_service(service, task)
    asyncio.run(scenario())
