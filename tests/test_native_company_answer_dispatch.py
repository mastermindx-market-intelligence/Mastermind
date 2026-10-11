"""Real Runtime/Relay/Wake composition; provider and MCP admission are synthetic."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace

import pytest

from control_plane.executive_runtime import StateConflict
from control_plane.executive_service import ExecutiveControlService, ExecutiveDialogueWakeBridge
from control_plane.operator_harness_contract import AttentionCompanyReadProjection
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.wake_dispatcher import TransportOutcome, TransportReceipt, WakeTransportCompletion
from control_plane.wake_ledger import LedgerPhase
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.slack_agent_dialogue.persisted_wake_carrier import PersistedWakeCarrier
from tests import test_company_inbox_iac1 as fixtures
from tests.test_company_consultation_host import composed, call
from tests.test_executive_wake_persisted_dispatch import _POLICY, _codex_registry
from tests.test_native_company_receipt import call as native_read, make_item, make_params, result_for


@pytest.mark.parametrize("mode", ["inline", "restart", "accepted", "unarmed", "retry_unarmed", "no_native", "consumer_hold"])
def test_reply_and_restart_use_one_existing_wake_carrier_and_exact_consumer(composed, monkeypatch, mode):
    async def scenario():
        with tempfile.TemporaryDirectory(prefix="c-dispatch-", dir="/tmp") as directory:
            socket = Path(directory) / "r.sock"
            service, task = await fixtures._start_relay_service(
                socket_path=socket, client=composed.client,
            )
            host = composed.build_host(socket)
            provider_calls, reconcile_calls, resolutions = [], [], []
            try:
                registry = replace(_codex_registry(), production_armed=mode != "unarmed")
                monkeypatch.setattr("control_plane.session_targets.load_session_targets", lambda: registry)
                def capability(self, attempt_id, *, connection=None, **kwargs):
                    if mode == "consumer_hold":
                        raise StateConflict("synthetic current MCP refusal")
                    return host._capability(attempt_id, connection=connection)
                monkeypatch.setattr(type(composed.runtime), "current_harness_mcp_binding_for_attempt", capability)

                class Provider:
                    transport_id = "codex-app-server"
                    async def nudge(self, wake):
                        provider_calls.append(wake.nudge_id)
                        if mode == "accepted":
                            return TransportReceipt(outcome=TransportOutcome.ACCEPTED,
                                reason_code="accepted", created_at="2026-09-14T00:00:00Z",
                                details=(("nudge_id", wake.nudge_id),))
                        return await self.completion(wake)
                    async def reconcile(self, wake):
                        reconcile_calls.append(wake.nudge_id)
                        return await self.completion(wake)
                    async def completion(self, wake):
                        returned = await call(host, composed.a[1], "company.consultation",
                                              {"consultation_ref": ref})
                        assert returned["ok"], returned
                        binding = host._caller(host._capability(composed.a[1])).binding
                        native = native_read(make_params(
                            thread_id=binding.native_handle, turn_id="turn-answer",
                            item=make_item(arguments={"consultation_ref": ref}, result=result_for(returned)),
                        ), thread=binding.native_handle, turn="turn-answer")
                        assert native is not None
                        binding = host._caller(host._capability(composed.a[1])).binding
                        evidence = AttentionCompanyReadProjection(
                            target_attempt_id=composed.a[1],
                            process_generation_id=host._capability(composed.a[1]).binding.process_generation_id,
                            binding_id=binding.binding_id, binding_generation=binding.binding_generation,
                            provider_session_id=binding.native_handle, provider_native_turn_id="turn-answer",
                            nudge_id=wake.nudge_id, consultation_ref=ref,
                            result_sha256=native["result_sha256"], native_item_sha256=native["native_item_sha256"],
                            answer_attestation_sha256=native["answer_attestation_sha256"],
                        )
                        return WakeTransportCompletion(
                            receipt=TransportReceipt(outcome=TransportOutcome.DELIVERED,
                                reason_code="delivered", created_at="2026-09-14T00:00:00Z",
                                details=(("nudge_id", wake.nudge_id),)),
                            company_read_projection=None if mode == "no_native" else evidence,
                        )
                def factory(**values):
                    resolutions.append(values["resolved"])
                    assert values["resolved"].target_attempt_id == composed.a[1]
                    def current(_route):
                        values["source_guard"]()
                        return project_runtime_binding(composed.runtime, composed.a[1], values["target"])
                    return PersistedWakeCarrier(
                        repository=WakeLedgerRepository(composed.runtime),
                        dispatchers=WakeDispatcherRegistry({"codex-app-server": Provider()}),
                        current_binding_for=current, retry_policy=values["retry_policy"],
                        target_registry=values["resolved"].registry,
                    )
                bridge = ExecutiveDialogueWakeBridge(
                    target_provider=None, retry_policy=replace(_POLICY, armed=mode != "retry_unarmed"),
                    carrier_factory=factory, operator_adapter=SimpleNamespace(deliver_attention=lambda *args: None),
                )
                dispatch_errors = []
                async def dispatch(projection):
                    try:
                        return await bridge.dispatch_requester_answer(composed.runtime, projection)
                    except Exception as exc:
                        dispatch_errors.append((type(exc).__name__, str(exc)))
                        raise
                if mode != "restart":
                    host._requester_answer_wake_dispatch = dispatch

                peers = await call(host, composed.a[1], "company.peers", {})
                args = fixtures._consult_args(question="One requester Wake.", evidence_refs=[],
                                              artifact_revisions=[composed.revision])
                args["to"] = peers["data"]["peers"][0]["peer_ref"]
                question = await call(host, composed.a[1], "company.consult", args)
                assert question["ok"], question
                ref = question["data"]["consultation_ref"]
                fixtures._deliver_and_ack_wake_path(composed.runtime, ref)
                answer = await call(host, composed.b[1], "company.reply",
                                    {"consultation_ref": ref, "answer": "Exact answer.", "evidence_refs": []})
                assert answer["ok"], (answer, composed.failures)
                if mode == "restart":
                    assert not provider_calls
                    host._requester_answer_wake_dispatch = dispatch
                # Exercise the existing service-owned recovery pass without a
                # launchd process. No test grants production host authority.
                control = ExecutiveControlService.__new__(ExecutiveControlService)
                control.runtime, control._company_consultation_host = composed.runtime, host
                control._service_state, control._closing = "READY", False
                control._company_consultation_binding = object()
                control._company_consultation_ready = True
                control.config = SimpleNamespace(coo_operator_harness_armed=True, coo_autonomy_armed=False)
                await control._reconcile_company_answer_wakes()
                await control._reconcile_company_answer_wakes()
                consumed = fixtures._consultation_event_count(composed.runtime, ref, "CONSUMED_BY_REQUESTER")
                if mode in {"unarmed", "retry_unarmed"}:
                    assert not provider_calls and not resolutions and consumed == 0
                    assert control._company_answer_reconciliation[0]["state"] == "HELD"
                else:
                    assert len(provider_calls) == 1, (dispatch_errors, control._company_answer_reconciliation, len(resolutions))
                    assert len(reconcile_calls) == int(mode == "accepted")
                    assert consumed == (1 if mode in {"inline", "restart", "accepted"} else 0)
                    rows = [row for row in WakeLedgerRepository(composed.runtime).list_wake_events()
                            if row.record.native_company_read is not None]
                    assert len(rows) == (0 if mode == "no_native" else 1)
                    if rows:
                        assert rows[0].record.phase is LedgerPhase.DELIVERED
                    if mode == "consumer_hold":
                        assert control._company_answer_reconciliation[0]["state"] == "HELD"
            finally:
                await fixtures._stop_relay_service(service, task)
    asyncio.run(scenario())
