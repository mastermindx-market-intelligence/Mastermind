"""Strict native lifecycle composition: revisions, confirmation and original effects."""
import asyncio
import copy
import unittest
from dataclasses import replace

from integrations.session_bridge.t3_native_client import (
    Conflict, EffectUnknown, LifecycleSnapshot, Rejected, Scope, Thread,
    T3NativeClient, Unavailable,
)

SCOPE = Scope("original-connection", "environment-1", "project-1")
THREAD = Thread(SCOPE, "thread-1")
SCHEMAS = {
    "t3_thread_lifecycle": {"type": "object", "properties": {
        "action": {"enum": ["inspect", "delete", "set_model"]}, "threadId": {}, "environmentId": {},
        "expectedSequence": {}, "expectedTitle": {}, "modelSelection": {}, "expectedUpdatedAt": {},
    }},
    "orchestrator_capabilities": {"type": "object", "properties": {"environmentId": {}, "search": {}}},
}


class Native:
    def __init__(self):
        self.calls = []
        self.state = dict(threadId="thread-1", projectId="project-1", title="Original title",
                          expectedSequence=40, updatedAt="2026-11-09T18:00:00Z",
                          modelSelection=dict(instanceId="capacity_fabric", model="logical-1"),
                          archived=False, deleted=False)
        self.mutation_result = None
        self.unavailable = False
        self.readback_error = None
        self.wrote = False

    async def __call__(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == "orchestrator_capabilities":
            body = dict(providers=[dict(providerInstanceId="capacity_fabric", canRunChildTask=not self.unavailable,
                        constraints=[], models=[{"id": "logical-1"}, {"id": "logical-2"}])])
        elif name == "t3_thread_lifecycle" and args["action"] == "inspect":
            if self.wrote and self.readback_error is not None:
                raise self.readback_error
            body = copy.deepcopy(self.state)
        elif name == "t3_thread_lifecycle":
            if self.mutation_result is not None:
                if isinstance(self.mutation_result, BaseException):
                    raise self.mutation_result
                return copy.deepcopy(self.mutation_result)
            if args["expectedSequence"] != self.state["expectedSequence"]:
                return dict(isError=True, structuredContent={"code": "thread_conflict"})
            self.wrote = True
            self.state["expectedSequence"] += 1
            if args["action"] == "set_model":
                self.state["modelSelection"] = copy.deepcopy(args["modelSelection"])
            else:
                self.state["deleted"] = True
            body = dict(commandId="native:command:original", sequence=self.state["expectedSequence"])
        else:
            raise AssertionError(name)
        return dict(structuredContent=body, isError=False)


class LifecycleClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.native = Native()
        self.client = T3NativeClient(SCOPE, self.native, SCHEMAS)
        self.snapshot = await self.client.lifecycle_snapshot(THREAD)
        self.native.calls.clear()

    async def delete(self, **overrides):
        args = dict(request_id="original-delete", confirmation_title=self.snapshot.title, confirm_delete=True)
        args.update(overrides)
        return await self.client.delete(self.snapshot, **args)

    async def test_discovered_strict_snapshot_is_original_scoped_and_revisioned(self):
        self.assertEqual(self.snapshot, LifecycleSnapshot(THREAD, 40, "Original title", "2026-11-09T18:00:00Z",
                                                        "capacity_fabric", "logical-1", False, False))
        self.assertTrue(self.client.capabilities()["confirmed_delete"])
        self.assertTrue(self.client.capabilities()["atomic_model_selection"])

    async def test_delete_requires_explicit_exact_title_confirmation_before_any_call(self):
        for values in ({"confirm_delete": False}, {"confirm_delete": 1}, {"confirmation_title": "Other"}):
            with self.subTest(values=values):
                with self.assertRaises((ValueError, Conflict)):
                    await self.delete(**values)
        self.assertFalse(self.native.calls)

    async def test_delete_uses_native_tombstone_only_without_provider_health_dependency(self):
        self.native.unavailable = True
        result = await self.delete()
        self.assertEqual(result["receipt"]["commandId"], "native:command:original")
        self.assertTrue(result["native_atomic_precondition"])
        self.assertTrue(result["retained_tombstone_only"])
        self.assertEqual([n for n, _ in self.native.calls], ["t3_thread_lifecycle"] * 2)
        self.assertEqual(self.native.calls[-1][1], dict(action="delete", threadId="thread-1", expectedSequence=40,
                         expectedTitle="Original title", environmentId="environment-1"))
        self.assertTrue(self.native.state["deleted"])

    async def test_same_timestamp_and_title_but_different_revision_refuses_before_write(self):
        self.native.state["expectedSequence"] = 42
        with self.assertRaises(Conflict):
            await self.delete()
        self.assertEqual(len(self.native.calls), 1)
        self.assertFalse(self.native.wrote)

    async def test_forged_snapshot_cannot_escape_actual_native_project(self):
        self.native.state["projectId"] = "other-project"
        with self.assertRaises(Conflict):
            await self.delete()
        self.assertEqual(len(self.native.calls), 1)
        self.assertFalse(self.native.wrote)

    async def test_foreign_connection_is_refused_without_call(self):
        foreign = replace(self.snapshot, thread=Thread(Scope("foreign", "environment-1", "project-1"), "thread-1"))
        with self.assertRaises(Conflict):
            await self.client.delete(foreign, request_id="x", confirmation_title=foreign.title, confirm_delete=True)
        self.assertFalse(self.native.calls)

    async def test_exact_capacity_model_and_receipt_readback_are_required(self):
        result = await self.client.set_model_atomic(self.snapshot, request_id="model-original", model="logical-2")
        self.assertEqual(result["observed"].model, "logical-2")
        self.assertEqual(result["observed"].sequence, 41)
        self.assertEqual(self.native.calls[-2][1]["modelSelection"], {"instanceId": "capacity_fabric", "model": "logical-2"})
        self.assertEqual(self.native.calls[-2][1]["expectedSequence"], 40)
        self.assertEqual([a.get("action") for n, a in self.native.calls if n == "t3_thread_lifecycle"],
                         ["inspect", "set_model", "inspect"])

    async def test_unready_capacity_never_falls_back_or_changes_model(self):
        self.native.unavailable = True
        with self.assertRaises(Rejected):
            await self.client.set_model_atomic(self.snapshot, request_id="model-original", model="logical-2")
        self.assertEqual([n for n, _ in self.native.calls], ["orchestrator_capabilities"])

    async def test_foreign_provider_or_archived_target_cannot_be_reselected(self):
        for snapshot in (replace(self.snapshot, provider_id="other"), replace(self.snapshot, archived=True),
                         replace(self.snapshot, deleted=True)):
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(Conflict):
                    await self.client.set_model_atomic(snapshot, request_id="model-original", model="logical-2")
        self.assertFalse(self.native.calls)

    async def test_failed_model_readback_retains_original_committed_receipt_without_retry(self):
        self.native.readback_error = OSError("lost original readback")
        with self.assertRaises(EffectUnknown) as result:
            await self.client.set_model_atomic(self.snapshot, request_id="model-original", model="logical-2")
        self.assertEqual(result.exception.receipt, {"commandId": "native:command:original", "sequence": 41})
        self.assertEqual(result.exception.request_id, "model-original")
        self.assertEqual(sum(a.get("action") == "set_model" for _, a in self.native.calls), 1)

    async def test_missing_or_nonadvancing_receipt_is_unknown_not_success(self):
        for body in ({"sequence": 41}, {"commandId": "native-command", "sequence": 40},
                     {"commandId": "native-command", "sequence": True}):
            with self.subTest(body=body):
                self.native.calls.clear()
                self.native.mutation_result = dict(structuredContent=body, isError=False)
                with self.assertRaises(EffectUnknown) as result:
                    await self.delete()
                self.assertEqual(result.exception.receipt, body)
                self.assertEqual(len(self.native.calls), 2)

    async def test_cancellation_does_not_replay_or_start_replacement(self):
        self.native.mutation_result = asyncio.CancelledError()
        with self.assertRaises(EffectUnknown) as result:
            await self.delete()
        self.assertEqual(result.exception.request_id, "original-delete")
        self.assertEqual(result.exception.thread_id, THREAD.thread_id)
        self.assertEqual(len(self.native.calls), 2)

    async def test_explicit_native_permission_denial_remains_denial(self):
        self.native.mutation_result = dict(isError=True, structuredContent={"code": "capability_denied"})
        with self.assertRaises(Rejected) as result:
            await self.delete()
        self.assertEqual(result.exception.code, "capability_denied")
        self.assertEqual(len(self.native.calls), 2)

    async def test_generic_native_error_is_not_misclassified_as_safe_to_repeat(self):
        self.native.mutation_result = dict(isError=True, structuredContent={"code": "orchestration_error"})
        with self.assertRaises(EffectUnknown):
            await self.delete()
        self.assertEqual(len(self.native.calls), 2)

    async def test_timestamp_only_or_malformed_catalog_never_grants_atomic_operations(self):
        variants = [{}, {"t3_thread_control": SCHEMAS["t3_thread_lifecycle"]}]
        for missing in ("expectedSequence", "expectedTitle", "modelSelection"):
            value = copy.deepcopy(SCHEMAS); del value["t3_thread_lifecycle"]["properties"][missing]; variants.append(value)
        for action in ({"enum": ["delete", "set_model"]}, {"enum": [[]]}, "bad"):
            value = copy.deepcopy(SCHEMAS); value["t3_thread_lifecycle"]["properties"]["action"] = action; variants.append(value)
        for schemas in variants:
            with self.subTest(schemas=schemas):
                client = T3NativeClient(SCOPE, self.native, schemas)
                self.assertFalse(client.capabilities()["lifecycle_extension"])
                with self.assertRaises(Unavailable):
                    await client.delete(self.snapshot, request_id="original", confirmation_title=self.snapshot.title, confirm_delete=True)
        self.assertFalse(self.native.calls)

    async def test_malformed_native_snapshot_cannot_be_used_as_confirmation(self):
        original = copy.deepcopy(self.native.state)
        for field, value in [("expectedSequence", True), ("expectedSequence", -1), ("title", None),
                             ("archived", 0), ("deleted", "false"), ("modelSelection", {})]:
            with self.subTest(field=field):
                self.native.state = copy.deepcopy(original); self.native.state[field] = value
                with self.assertRaises(Unavailable):
                    await self.client.lifecycle_snapshot(THREAD)

    async def test_empty_native_title_can_be_confirmed_exactly(self):
        self.native.state["title"] = ""
        self.snapshot = await self.client.lifecycle_snapshot(THREAD)
        result = await self.delete()
        self.assertEqual(result["receipt"]["sequence"], 41)

    async def test_nonboolean_error_flag_cannot_smuggle_native_success(self):
        self.native.mutation_result = dict(isError=0, structuredContent={"commandId": "command", "sequence": 41})
        with self.assertRaises(EffectUnknown):
            await self.delete()


if __name__ == "__main__":
    unittest.main()
