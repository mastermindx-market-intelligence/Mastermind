"""Source-only tests of Hermes -> EXISTING original-parent native reply writer.

No Slack API, Hermes subprocess, token file, proxy, provider or Fabric call.
"""
import asyncio
import copy
import dataclasses
from pathlib import Path
import unittest

from integrations.hermes_secretary.native_dialogue_consumer import (
    ConsumerRefusal, HermesCanonicalTurnConsumer,
)
from integrations.session_bridge.native_reply import NativeReplyBinding, NativeReplyWriter
from integrations.session_bridge.schemas import BridgeError
from integrations.slack_agent_dialogue.contract_v2 import MESSAGE_SCHEMA_V2, build_message_v2
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import DialogueServiceError

NATIVE = "11111111-2222-4444-8888-999999999999"
THREAD = "1787896128.625239"
OP = "hermes-native-return-001"
REQUEST = "asd-executive-continue-0001"
COMMISSION = {
    "repository": "mastermindx-market-intelligence/Mastermind",
    "commit": "1" * 40,
    "path": "docs/superpowers/plans/session-bridge.md",
    "content_sha256": "2" * 64,
}
APPLIES = {"kind": "executive_attempt", "job_id": "JOB-001", "attempt_id": "ATT-001", "worker_id": "W-001"}
ACTOR = {"kind": "worker_attempt", "job_id": "JOB-001", "attempt_id": "ATT-001", "worker_id": "W-001"}


def _binding():
    return NativeReplyBinding(
        native_session_id=NATIVE, binding_id="bind-native-001", binding_generation=1,
        process_generation_id="generation-001", thread_ts=THREAD,
        request_message_key=REQUEST, reply_operation_key=OP,
        context=DialogueContextV2(
            work_ref="WS:DOT-BRIDGE", commission_ref=COMMISSION,
            session_ref="asd-session-dotbridge01", operation_key="dialogue-parent-001",
            watch_mode="turn_watch_v1", actor_ref=ACTOR, applies_to=APPLIES,
        ),
    )


def _request(summary="Continue bounded work.", body=None):
    return build_message_v2({
        "schema": MESSAGE_SCHEMA_V2, "message_key": REQUEST,
        "message_type": "CONTINUE", "work_ref": "WS:DOT-BRIDGE",
        "commission_ref": COMMISSION, "session_ref": "asd-session-dotbridge01",
        "actor_ref": {"kind": "executive_surface", "seat": "ceo", "reasoning_surface": "chatgpt"},
        "reply_to_message_key": "asd-worker-result-0001",
        "applies_to": APPLIES, "summary": summary,
        "body": body or {"instruction": "Read the canonical question.",
                         "stop_condition": "Return the finding.", "scope_change": False},
        "evidence_refs": [], "requires_response": False, "created_at": "2026-10-01T20:00:00Z",
    })


class Resolver:
    def __init__(self):
        self.binding = _binding()
        self.calls = 0

    def resolve(self, **_):
        self.calls += 1
        return self.binding


class Service:
    def __init__(self):
        self.items = [{"message": _request(), "primary_ts": "1787896130.000001"}]
        self.calls = []
        self.on_read = None
        self.send_exception = None

    async def __call__(self, path, payload, *, before_write=None):
        if payload["operation"] == "send_message" and before_write:
            await before_write()
        self.calls.append(copy.deepcopy(payload))
        if payload["operation"] == "read_thread":
            if self.on_read:
                self.on_read()
            return {"ok": True, "result": {
                "thread_ts": THREAD, "messages": copy.deepcopy(self.items),
                "historical_messages": [], "mutated_count": 0, "ineligible_count": 0,
            }}
        if self.send_exception:
            raise self.send_exception
        message = payload["args"]["message"]
        self.items.append({"message": copy.deepcopy(message), "primary_ts": "1787896140.000001"})
        return {"ok": True, "result": {
            "action": "POSTED", "message_key": message["message_key"],
            "fingerprint": message["fingerprint"],
        }}


class Model:
    def __init__(self):
        self.prompts = []
        self.response = "Found the requested source and verified its status."
        self.error = None
        self.on_infer = None

    async def __call__(self, prompt):
        self.prompts.append(prompt)
        if self.on_infer:
            self.on_infer()
        if self.error:
            raise self.error
        return self.response


class ConsumerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.resolver = Resolver()
        self.service = Service()
        self.model = Model()
        self.role = "mmsecretary"
        self.current = lambda _session: self.role
        self.writer = NativeReplyWriter(
            self.resolver, native_session_id=NATIVE,
            socket_path=Path("/private/tmp/hermes-canonical-test.sock"),
            service_call=self.service,
        )

    def consumer(self, role="mmsecretary", model=None, current=None, writer=None):
        return HermesCanonicalTurnConsumer(
            role=role, native_session_id=NATIVE,
            reply_writer=writer or self.writer,
            current_role=current or self.current,
            infer_text=model or self.model,
        )

    async def run_turn(self, **args):
        return await self.consumer().run(operation_key=OP, in_reply_to=REQUEST, **args)

    def send_count(self):
        return sum(c["operation"] == "send_message" for c in self.service.calls)

    async def test_exact_canonical_parent_and_single_message(self):
        answer = await self.run_turn()
        self.assertEqual(answer["status"], "CANONICAL_REPLY_COMMITTED")
        self.assertFalse(answer["parent_consumed"])
        self.assertFalse(answer["role_bot_slack_delivery_verified"])
        self.assertEqual(answer["thread_ts"], THREAD)
        self.assertEqual(len(self.model.prompts), 1)
        self.assertIn("Read the canonical question.", self.model.prompts[0])
        self.assertEqual(self.send_count(), 1)
        payload = self.service.calls[-1]
        self.assertEqual(payload["args"]["send_protocol"], "mastermind.agent_dialogue_exact_send.v1")
        self.assertEqual(payload["args"]["message"]["reply_to_message_key"], REQUEST)
        self.assertEqual(payload["args"]["message"]["actor_ref"], ACTOR)
        self.assertEqual(payload["args"]["message"]["body"]["completed"], self.model.response)

    async def test_second_invocation_does_not_infer_or_resend(self):
        await self.run_turn()
        again = await self.run_turn()
        self.assertEqual(again["status"], "ALREADY_REPLIED_CANONICALLY")
        self.assertFalse(again["new_model_call"])
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(self.send_count(), 1)

    async def test_injected_routing_or_text_is_refused(self):
        with self.assertRaises(TypeError):
            await self.run_turn(thread_ts="9999999999.000001")
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.send_count(), 0)

    async def test_invalid_requested_message_identity_is_refused(self):
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.consumer().run(operation_key="bad op", in_reply_to=REQUEST)
        self.assertEqual(cm.exception.code, "CALLER_IDENTITY_INVALID")
        self.assertEqual(self.model.prompts, [])

    async def test_wrong_role_on_live_host_refuses_before_inference(self):
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.consumer(role="mmmeta").run(operation_key=OP, in_reply_to=REQUEST)
        self.assertEqual(cm.exception.code, "ROLE_CURRENT_BINDING_REFUSED")
        self.assertEqual(self.model.prompts, [])

    async def test_unknown_role_cannot_construct(self):
        with self.assertRaises(ConsumerRefusal):
            self.consumer(role="grok-secretary")
        self.assertEqual(self.model.prompts, [])

    async def test_non_ceo_request_refused_before_inference(self):
        # The schema itself refuses COO-origin CONTINUE. Supply a genuine
        # *valid* worker PROGRESS frame with the original key instead to prove
        # this consumer cannot promote other canonical messages into orders.
        msg = _request()
        msg["message_type"] = "PROGRESS"
        msg["actor_ref"] = ACTOR
        msg["body"] = {"stage": "working", "completed": "none", "next": "hold"}
        msg.pop("fingerprint")
        self.service.items[0]["message"] = build_message_v2(msg)
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.run_turn()
        self.assertEqual(cm.exception.code, "ORIGINAL_REQUEST_NOT_AUTHORIZED")
        self.assertEqual(self.send_count(), 0)

    async def test_newer_executive_message_cannot_be_ignored(self):
        second = _request()
        second["message_key"] = "asd-executive-continue-0002"
        second.pop("fingerprint")
        self.service.items.append({"primary_ts": "1787896131.000001",
                                   "message": build_message_v2(second)})
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.run_turn()
        self.assertEqual(cm.exception.code, "ORIGINAL_REQUEST_SUPERSEDED")
        self.assertEqual(len(self.model.prompts), 0)


    def synchronous_model(self, prompt):
        # Record entry itself: the callback may have an effect before returning
        # an awaitable, so counting only awaited work would be insufficient.
        self.model.prompts.append(prompt)
        return self.model.response

    async def test_role_drift_during_canonical_read_refuses_model_entry(self):
        self.service.on_read = lambda: setattr(self, "role", "mmmeta")
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.consumer(model=self.synchronous_model).run(
                operation_key=OP, in_reply_to=REQUEST)
        self.assertEqual(cm.exception.code, "ROLE_CHANGED_BEFORE_MODEL_TURN")
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.send_count(), 0)

    async def test_binding_generation_drift_during_read_refuses_model_entry(self):
        self.service.on_read = lambda: setattr(
            self.resolver, "binding",
            dataclasses.replace(self.resolver.binding, binding_generation=2))
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.consumer(model=self.synchronous_model).run(
                operation_key=OP, in_reply_to=REQUEST)
        self.assertEqual(cm.exception.code, "BINDING_CHANGED_BEFORE_MODEL_TURN")
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.send_count(), 0)

    async def test_process_generation_drift_during_read_refuses_model_entry(self):
        self.service.on_read = lambda: setattr(
            self.resolver, "binding",
            dataclasses.replace(self.resolver.binding, process_generation_id="generation-002"))
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.consumer(model=self.synchronous_model).run(
                operation_key=OP, in_reply_to=REQUEST)
        self.assertEqual(cm.exception.code, "BINDING_CHANGED_BEFORE_MODEL_TURN")
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.send_count(), 0)

    async def test_scope_drift_without_generation_change_refuses_model_entry(self):
        original = self.resolver.binding
        def change_scope():
            self.resolver.binding = dataclasses.replace(
                original, context=dataclasses.replace(
                    original.context, work_ref="WS:OUT-OF-SCOPE"))
        self.service.on_read = change_scope
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.consumer(model=self.synchronous_model).run(
                operation_key=OP, in_reply_to=REQUEST)
        self.assertEqual(cm.exception.code, "BINDING_CHANGED_BEFORE_MODEL_TURN")
        self.assertEqual(self.resolver.binding.native_session_id, original.native_session_id)
        self.assertEqual(self.resolver.binding.binding_generation, original.binding_generation)
        self.assertEqual(self.resolver.binding.process_generation_id, original.process_generation_id)
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.send_count(), 0)

    async def test_binding_unavailable_after_read_refuses_model_entry(self):
        self.service.on_read = lambda: setattr(self.resolver, "binding", None)
        with self.assertRaises(BridgeError) as cm:
            await self.consumer(model=self.synchronous_model).run(
                operation_key=OP, in_reply_to=REQUEST)
        self.assertEqual(cm.exception.code, "binding_unavailable")
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.send_count(), 0)

    async def test_role_source_failure_after_read_refuses_model_entry(self):
        state = {"read": False}
        self.service.on_read = lambda: state.update(read=True)
        def current(_session):
            if state["read"]:
                raise RuntimeError("SYNTHETIC_PRIVATE_ROLE_DIAGNOSTIC")
            return self.role
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.consumer(model=self.synchronous_model, current=current).run(
                operation_key=OP, in_reply_to=REQUEST)
        self.assertEqual(cm.exception.code, "ROLE_BINDING_UNAVAILABLE")
        self.assertNotIn("SYNTHETIC_PRIVATE_ROLE_DIAGNOSTIC", str(cm.exception))
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.send_count(), 0)

    async def test_role_drift_during_binding_recheck_refuses_model_entry(self):
        original_resolve = self.resolver.resolve
        calls = 0
        async def resolve(**arguments):
            nonlocal calls
            calls += 1
            if calls == 2:
                await asyncio.sleep(0)
                self.role = "mmmeta"
            return original_resolve(**arguments)
        self.resolver.resolve = resolve
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.consumer(model=self.synchronous_model).run(
                operation_key=OP, in_reply_to=REQUEST)
        self.assertEqual(cm.exception.code, "ROLE_CHANGED_BEFORE_MODEL_TURN")
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.send_count(), 0)

    async def assert_check_cancellation(self, entered, *, current=None):
        pending = asyncio.create_task(self.consumer(
            model=self.synchronous_model, current=current).run(
                operation_key=OP, in_reply_to=REQUEST))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
            self.assertTrue(pending.cancelled())
            self.assertEqual(self.model.prompts, [])
            self.assertEqual(self.send_count(), 0)
        finally:
            if not pending.done():
                pending.cancel()
                try:
                    await pending
                except asyncio.CancelledError:
                    pass

    async def test_cancellation_during_binding_recheck_has_no_model_effect(self):
        original_resolve = self.resolver.resolve
        entered, held = asyncio.Event(), asyncio.Event()
        calls = 0
        async def resolve(**arguments):
            nonlocal calls
            calls += 1
            if calls == 2:
                entered.set()
                await held.wait()
            return original_resolve(**arguments)
        self.resolver.resolve = resolve
        await self.assert_check_cancellation(entered)

    async def test_cancellation_during_role_recheck_has_no_model_effect(self):
        entered, held = asyncio.Event(), asyncio.Event()
        calls = 0
        async def current(_session):
            nonlocal calls
            calls += 1
            if calls == 2:
                entered.set()
                await held.wait()
            return self.role
        await self.assert_check_cancellation(entered, current=current)

    async def test_current_host_role_change_during_inference_holds_send(self):
        self.model.on_infer = lambda: setattr(self, "role", "mmmeta")
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.run_turn()
        self.assertEqual(cm.exception.code, "ROLE_CHANGED_DURING_MODEL_TURN")
        self.assertEqual(self.send_count(), 0)

    async def test_current_binding_change_during_inference_holds_send(self):
        self.model.on_infer = lambda: setattr(self.resolver, "binding",
                                               dataclasses.replace(self.resolver.binding,
                                                                   binding_generation=2))
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.run_turn()
        self.assertEqual(cm.exception.code, "BINDING_CHANGED_DURING_MODEL_TURN")
        self.assertEqual(self.send_count(), 0)

    async def test_role_resolver_error_is_redacted_before_inference(self):
        def broken(_session):
            raise RuntimeError("SECRET_PRIVATE_HOST_BINDING_DETAIL")
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.consumer(current=broken).run(operation_key=OP, in_reply_to=REQUEST)
        self.assertEqual(cm.exception.code, "ROLE_BINDING_UNAVAILABLE")
        self.assertNotIn("PRIVATE_HOST", str(cm.exception))
        self.assertEqual(self.model.prompts, [])

    async def test_secret_in_original_request_refused_before_inference(self):
        self.service.items[0]["message"] = _request(
            body={"instruction": "api_key=DO_NOT_EGRESS_THIS_VALUE",
                  "stop_condition": "Return receipt.", "scope_change": False})
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.run_turn()
        self.assertEqual(cm.exception.code, "CANONICAL_PROMPT_SECRET_REFUSED")
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.send_count(), 0)

    async def test_model_failure_does_not_expose_error_or_post(self):
        self.model.error = RuntimeError("SENSITIVE_PRIVATE_PROVIDER_TOKEN")
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.run_turn()
        self.assertEqual(cm.exception.code, "MODEL_TURN_FAILED")
        self.assertNotIn("SENSITIVE_PRIVATE", str(cm.exception))
        self.assertEqual(self.send_count(), 0)

    async def test_secret_in_response_never_goes_to_slack(self):
        self.model.response = "api_key=PROVIDER_PRIVATE_SENTINEL"
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.run_turn()
        self.assertEqual(cm.exception.code, "MODEL_REPLY_UNQUALIFIED")
        self.assertEqual(self.send_count(), 0)

    async def test_oversize_response_refused(self):
        self.model.response = "a" * 701
        with self.assertRaises(ConsumerRefusal):
            await self.run_turn()
        self.assertEqual(self.send_count(), 0)

    async def test_missing_original_request_refuses_without_inference(self):
        self.service.items = []
        with self.assertRaises(ConsumerRefusal) as cm:
            await self.run_turn()
        self.assertEqual(cm.exception.code, "ORIGINAL_REQUEST_NOT_CURRENT")
        self.assertEqual(self.model.prompts, [])

    async def test_opaque_reply_key_collision_with_foreign_actor_refuses(self):
        # First canonical response, then mutate actor to an unrelated worker.
        await self.run_turn()
        self.service.items[-1]["message"]["actor_ref"] = {
            "kind": "worker_attempt", "job_id": "JOB-222",
            "attempt_id": "ATT-222", "worker_id": "W-222",
        }
        with self.assertRaises(BridgeError):
            await self.run_turn()
        self.assertEqual(self.send_count(), 1)

    async def test_send_effect_unknown_never_retries(self):
        self.service.send_exception = DialogueServiceError("SEND_EFFECT_UNKNOWN")
        with self.assertRaises(BridgeError) as cm:
            await self.run_turn()
        self.assertEqual(cm.exception.code, "carrier_effect_unknown")
        self.assertEqual(self.send_count(), 1)
        self.assertEqual(len(self.model.prompts), 1)

    async def test_model_prompt_not_minted_from_slack_text(self):
        # There is no API for untyped Slack messages or channel IDs.
        candidate = self.consumer()
        self.assertFalse(hasattr(candidate, "scan_slack"))
        self.assertFalse(hasattr(candidate, "post_message"))
        self.assertFalse(hasattr(candidate, "submit_fabric"))



    async def test_quoted_credentials_in_canonical_fields_refuse_before_inference(self):
        samples = (
            '{"password":"SYNTHETIC_QUOTED_SECRET"}',
            '{"api_key": "SYNTHETIC_QUOTED_SECRET"}',
            "'token': 'SYNTHETIC_QUOTED_SECRET'",
            '"authorization" = "SYNTHETIC_QUOTED_SECRET"',
        )
        for field in ("summary", "instruction", "stop_condition"):
            for sample in samples:
                with self.subTest(field=field, sample_format=samples.index(sample)):
                    self.setUp()
                    body = {"instruction": "Read source.", "stop_condition": "Return receipt.", "scope_change": False}
                    summary = "Continue bounded work."
                    if field == "summary":
                        summary = sample
                    else:
                        body[field] = sample
                    self.service.items[0]["message"] = _request(summary=summary, body=body)
                    with self.assertRaises(ConsumerRefusal) as cm:
                        await self.run_turn()
                    self.assertEqual(cm.exception.code, "CANONICAL_PROMPT_SECRET_REFUSED")
                    self.assertNotIn("SYNTHETIC_QUOTED_SECRET", str(cm.exception))
                    self.assertEqual(self.model.prompts, [])
                    self.assertEqual(self.send_count(), 0)

    async def test_quoted_model_credentials_refuse_before_canonical_send(self):
        for sample in (
            '{"password":"SYNTHETIC_QUOTED_SECRET"}',
            '{"api_key": "SYNTHETIC_QUOTED_SECRET"}',
            "'token': 'SYNTHETIC_QUOTED_SECRET'",
            '"authorization" = "SYNTHETIC_QUOTED_SECRET"',
        ):
            with self.subTest(sample_format=sample.split(":", 1)[0]):
                self.setUp()
                self.model.response = sample
                with self.assertRaises(ConsumerRefusal) as cm:
                    await self.run_turn()
                self.assertEqual(cm.exception.code, "MODEL_REPLY_UNQUALIFIED")
                self.assertNotIn("SYNTHETIC_QUOTED_SECRET", str(cm.exception))
                self.assertEqual(len(self.model.prompts), 1)
                self.assertEqual(self.send_count(), 0)

    async def test_benign_quoted_text_and_json_still_reach_original_parent(self):
        for sample in ('{"status":"working"}', "'result': 'source verified'", 'The "token count" is 12.'):
            with self.subTest(sample=sample):
                self.setUp()
                self.service.items[0]["message"] = _request(summary=sample)
                self.model.response = sample
                result = await self.run_turn()
                self.assertEqual(result["status"], "CANONICAL_REPLY_COMMITTED")
                self.assertEqual(result["thread_ts"], THREAD)
                self.assertEqual(len(self.model.prompts), 1)
                self.assertEqual(self.send_count(), 1)


if __name__ == "__main__":
    unittest.main()
