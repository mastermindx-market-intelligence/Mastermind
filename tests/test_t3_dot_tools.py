import asyncio
import copy
import unittest

from integrations.session_bridge.t3_dot_tools import T3DotTools, TOOLS
from integrations.session_bridge.t3_native_client import (
    Scope, Thread, T3NativeClient, Rejected, Unavailable,
)
from test_t3_native_client import Native, SCHEMAS, SCOPE, THREAD, observation, item


def run(value):
    return asyncio.run(value)


BASE = {"environment_id": SCOPE.environment_id, "project_id": SCOPE.project_id}
TARGET = {**BASE, "thread_id": THREAD.thread_id}
LAUNCH = {**BASE, "operation_id": "launch-1", "title": "Bounded test", "prompt": "Read only",
          "model": "glm-5.3", "writable": False}


class Owner:
    def __init__(self, client):
        self.native_client = client
        self.checks = []
        self.deny_after = None
        self.deny_name = None
        self.principal = "original-account"

    async def authorize(self, principal, **kw):
        self.checks.append((principal, copy.deepcopy(kw)))
        if (principal != self.principal or kw["operation"] == self.deny_name
                or self.deny_after is not None and len(self.checks) > self.deny_after):
            raise Rejected("capability_denied")
        if kw["environment_id"] not in (None, SCOPE.environment_id):
            raise Rejected("capability_denied")

    async def environments(self, principal):
        return {"environments": [{"environment_id": SCOPE.environment_id, "status": "reachable"}]}

    async def projects(self, principal, environment_id, *, cursor, limit):
        return {"projects": [{"project_id": SCOPE.project_id}], "next_cursor": None}

    async def client(self, principal, environment_id, project_id):
        return self.native_client


class DotToolsTests(unittest.TestCase):
    def setUp(self):
        self.native = Native()
        self.client = T3NativeClient(SCOPE, self.native, SCHEMAS)
        self.owner = Owner(self.client)
        self.tools = T3DotTools(self.owner)

    def call(self, name, args, principal="original-account"):
        return run(self.tools.call(principal, name, args))

    def test_catalog_closed_distinct_and_copy(self):
        catalog = self.tools.catalog()
        self.assertEqual(len(catalog), 20)
        self.assertEqual(len({tool["name"] for tool in catalog}), 20)
        for tool in catalog:
            self.assertIs(tool["inputSchema"]["additionalProperties"], False)
        catalog[0]["name"] = "bad"
        self.assertEqual(self.tools.catalog()[0]["name"], "t3_fleet_environments")

    def test_no_shell_credentials_or_permission_overrides(self):
        for field in ("command", "url", "token", "runtime_mode", "provider", "host", "principal"):
            with self.subTest(field=field):
                value = self.call("t3_thread_launch", {**LAUNCH, field: "injected"})
                self.assertEqual(value["status"], "INVALID_ARGUMENT")
        self.assertFalse(self.native.calls)
        self.assertFalse(self.owner.checks)

    def test_authorization_before_native_observation(self):
        value = self.call("t3_thread_read", TARGET, principal="other-account")
        self.assertEqual(value["status"], "REJECTED")
        self.assertFalse(self.native.calls)
        self.assertNotIn("data", value)

    def test_read_revocation_suppresses_payload(self):
        self.owner.deny_after = 1
        value = self.call("t3_thread_read", TARGET)
        self.assertEqual(value["status"], "REJECTED")
        self.assertNotIn("data", value)

    def test_write_postcondition_revocation_preserves_unknown_effect(self):
        self.owner.deny_after = 1
        value = self.call("t3_thread_launch", LAUNCH)
        self.assertEqual(value["status"], "EFFECT_UNKNOWN")
        self.assertEqual(value["original"]["operation_id"], "launch-1")
        self.assertEqual(sum(name == "t3_thread_launch" for name, _ in self.native.calls), 1)

    def test_owner_cannot_retarget_project(self):
        value = self.call("t3_thread_read", {**TARGET, "project_id": "foreign-project"})
        self.assertEqual(value["status"], "CONFLICT")
        self.assertFalse(self.native.calls)

    def test_boolean_is_not_integer_and_limits_checked(self):
        for args in ({**TARGET, "limit": True}, {**TARGET, "limit": 101},
                     {**TARGET, "after_position": -1}, {**TARGET, "view": "secrets"}):
            self.assertEqual(self.call("t3_thread_read", args)["status"], "INVALID_ARGUMENT")
        self.assertFalse(self.native.calls)

    def test_array_and_mapping_malformed_input(self):
        for value in ([], None, "data", 7):
            self.assertEqual(self.call("t3_thread_read", value)["status"], "INVALID_ARGUMENT")

    def test_read_original_native_items(self):
        value = self.call("t3_thread_read", TARGET)
        self.assertEqual(value["status"], "OBSERVED")
        self.assertEqual(value["data"]["items"][0]["runId"], "run-1")
        self.assertIs(value["parent_accepted"], False)
        self.assertEqual(len(self.owner.checks), 2)

    def test_secret_like_text_redacted_reasoning_omitted(self):
        reasoning = item("private", pos=2)
        reasoning["type"] = "reasoning"
        self.native.detail = observation([item("authorization=abcdefghijklmnop"), reasoning])
        self.native.detail["nextPosition"] = 2
        value = self.call("t3_thread_read", TARGET)
        self.assertEqual(value["status"], "OBSERVED")
        self.assertTrue(value["redacted"])
        self.assertEqual(len(value["data"]["items"]), 1)
        self.assertEqual(value["data"]["items"][0]["text"], "[REDACTED]")

    def test_item_uses_original_native_paged_contract(self):
        value = self.call("t3_thread_item", {**TARGET, "run_id": "run-1", "item_id": "item-1"})
        self.assertEqual(value["status"], "OBSERVED")
        self.assertEqual(self.native.calls[-1][1]["itemId"], "item-1")
        self.assertEqual(value["data"]["items"][0]["text"], "done")

    def test_item_foreign_run_rejected(self):
        value = self.call("t3_thread_item", {**TARGET, "run_id": "foreign", "item_id": "item-1"})
        self.assertEqual(value["status"], "CONFLICT")

    def test_item_nonadvancing_offset_rejected(self):
        self.native.detail = observation([item("part", truncated=True)])
        value = self.call("t3_thread_item", {**TARGET, "run_id": "run-1", "item_id": "item-1", "text_offset": 5})
        self.assertEqual(value["status"], "CONFLICT")

    def test_launch_preserves_capacity_and_original_identity(self):
        value = self.call("t3_thread_launch", LAUNCH)
        self.assertEqual(value["status"], "OBSERVED")
        self.assertEqual(value["data"]["run_id"], "run-1")
        self.assertEqual(value["data"]["thread"]["scope"]["environment_id"], SCOPE.environment_id)
        self.assertEqual(self.native.calls[-1][1]["modelSelection"]["instanceId"], "capacity_fabric")
        self.assertIs(value["retry_allowed"], False)

    def test_launch_write_without_worktree_never_dispatches(self):
        value = self.call("t3_thread_launch", {**LAUNCH, "writable": True})
        self.assertEqual(value["status"], "INVALID_ARGUMENT")
        self.assertFalse(self.native.calls)

    def test_uncertain_launch_is_not_retried(self):
        self.native.responses["t3_thread_launch"] = TimeoutError("lost result")
        value = self.call("t3_thread_launch", LAUNCH)
        self.assertEqual(value["status"], "EFFECT_UNKNOWN")
        self.assertEqual(value["original"]["environment_id"], SCOPE.environment_id)
        self.assertEqual(value["original"]["operation_id"], "launch-1")
        self.assertEqual(sum(name == "t3_thread_launch" for name, _ in self.native.calls), 1)

    def test_cancellation_after_native_send_is_uncertain(self):
        self.native.responses["t3_thread_launch"] = asyncio.CancelledError()
        value = self.call("t3_thread_launch", LAUNCH)
        self.assertEqual(value["status"], "EFFECT_UNKNOWN")
        self.assertEqual(sum(name == "t3_thread_launch" for name, _ in self.native.calls), 1)

    def test_unknown_model_does_not_fallback(self):
        value = self.call("t3_thread_launch", {**LAUNCH, "model": "unavailable"})
        self.assertEqual(value["status"], "REJECTED")
        self.assertFalse(any(name == "t3_thread_launch" for name, _ in self.native.calls))

    def test_followup_is_same_thread_new_run(self):
        value = self.call("t3_thread_send", {**TARGET, "operation_id": "followup", "message": "More evidence", "mode": "queue"})
        self.assertEqual(value["status"], "OBSERVED")
        self.assertEqual(value["data"]["thread"]["thread_id"], THREAD.thread_id)
        self.assertEqual(value["data"]["run_id"], "run-2")
        self.assertEqual(value["data"]["delivery"], "queued")

    def test_original_result_not_latest_run(self):
        self.native.detail["thread"]["latestRunId"] = "run-2"
        value = self.call("t3_run_result", {**TARGET, "run": {
            "run_id": "run-1", "request_id": "launch-1", "delivery": "launched"}})
        self.assertEqual(value["status"], "OBSERVED")
        self.assertEqual(value["data"]["answer"], "done")
        self.assertEqual(value["data"]["run"]["run_id"], "run-1")
        self.assertIs(value["parent_accepted"], False)

    def test_snapshot_partial_not_false_all_green(self):
        value = self.call("t3_threads_snapshot", {"targets": [TARGET, {**TARGET, "environment_id": "unreachable"}]})
        self.assertEqual(value["status"], "OBSERVED")
        self.assertFalse(value["data"]["complete"])
        self.assertEqual([row["status"] for row in value["data"]["threads"]], ["OBSERVED", "REJECTED"])
        self.assertFalse(value["data"]["monitor_started"])

    def test_snapshot_rejects_duplicate_and_unbounded_targets(self):
        for targets in ([TARGET, TARGET], [TARGET] * 13, []):
            value = self.call("t3_threads_snapshot", {"targets": targets})
            self.assertEqual(value["status"], "INVALID_ARGUMENT")
        self.assertFalse(self.native.calls)

    def test_native_children_lineage_and_forks(self):
        rows = []
        for tid, parent, relation in [("thread-1", None, None), ("child", "thread-1", "subagent"),
                                      ("grandchild", "child", "subagent"), ("fork", "thread-1", "fork")]:
            rows.append({"threadId": tid, "projectId": SCOPE.project_id, "parentThreadId": parent,
                         "relationshipToParent": relation, "status": "completed", "latestRunId": "run-1"})
        self.native.responses["t3_thread_list"] = {"structuredContent": {
            "projectId": SCOPE.project_id, "threads": rows, "total": 4, "nextCursor": None}}
        value = self.call("t3_thread_children", TARGET)
        self.assertEqual(value["status"], "OBSERVED")
        self.assertEqual({row["thread_id"] for row in value["data"]["threads"]}, {"thread-1", "child", "grandchild"})
        self.assertFalse(value["data"]["atomic_snapshot"])

    def test_stop_requires_explicit_exact_run_or_all(self):
        value = self.call("t3_thread_stop", {**TARGET, "operation_id": "stop-1", "stop_all": False})
        self.assertEqual(value["status"], "INVALID_ARGUMENT")
        self.assertFalse(self.native.calls)
        value = self.call("t3_thread_stop", {**TARGET, "operation_id": "stop-1", "stop_all": False, "run_id": "run-1"})
        self.assertEqual(value["data"]["status"], "interrupt_requested")

    def test_delete_needs_boolean_and_exact_title_and_native_extension(self):
        snapshot = {"sequence": 4, "title": "Original", "updated_at": "2026-11-13T00:00:00Z",
                    "provider_id": "capacity_fabric", "model": "glm-5.3", "archived": False, "deleted": False}
        args = {**TARGET, "operation_id": "delete-1", "snapshot": snapshot, "confirmed_title": "Original"}
        self.assertEqual(self.call("t3_thread_delete", args)["status"], "INVALID_ARGUMENT")
        self.assertEqual(self.call("t3_thread_delete", {**args, "confirm_delete": False})["status"], "INVALID_ARGUMENT")
        self.assertEqual(self.call("t3_thread_delete", {**args, "confirm_delete": True, "confirmed_title": "Other"})["status"], "CONFLICT")
        self.assertEqual(self.call("t3_thread_delete", {**args, "confirm_delete": True})["status"], "UNAVAILABLE")
        self.assertFalse(any(name == "t3_thread_lifecycle" for name, _ in self.native.calls))

    def test_question_answer_never_approves_permission(self):
        schema = {"type": "object", "properties": {key: {} for key in ("threadId", "action", "requestId", "answers", "environmentId")}}
        self.client.schemas["t3_pending_request"] = schema
        self.native.responses["t3_pending_request"] = {"isError": True, "structuredContent": {"code": "unsupported_operation"}}
        value = self.call("t3_question_answer", {**TARGET, "operation_id": "answer-1", "question_id": "permission", "answers": {"q": "yes"}})
        self.assertEqual(value["status"], "REJECTED")
        self.assertFalse(any(args.get("action") == "respond" for _, args in self.native.calls))

    def test_unknown_tool_no_owner_or_native(self):
        value = self.call("t3_raw_shell", {})
        self.assertEqual(value["status"], "UNAVAILABLE")
        self.assertFalse(self.owner.checks)
        self.assertFalse(self.native.calls)


if __name__ == "__main__":
    unittest.main()
