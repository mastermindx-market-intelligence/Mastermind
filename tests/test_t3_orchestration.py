"""Behavioral proof for native-parent composition, not actual agent execution."""
import asyncio
import copy
from dataclasses import replace

import pytest

from integrations.session_bridge.t3_mission_brief import MissionBrief, Phase
from integrations.session_bridge.t3_native_client import Scope, Thread, T3NativeClient, Rejected, Conflict, EffectUnknown, Unavailable
from integrations.session_bridge.t3_orchestration import ChildBrief, Communication, NativeParent, model_options, check_parallel_write_scopes
from tests.test_t3_native_client import Native, SCHEMAS, schema, observation

SCOPE = Scope("native-connection", "env-1", "project-1")
PARENT = Thread(SCOPE, "parent-1")


def mission():
    return MissionBrief("mission", "Ship complete resilient chat",
        "https://github.com/example/repo/blob/" + "a" * 40 + "/docs/mission.md", "a" * 40,
        (Phase("backend", "Durable messages", ("Recover after restart",)),
         Phase("interface", "Responsive accessible chat", ("Keyboard and reconnect proof",))),
        ("Messages survive restart", "Mobile and desktop work", "Stop prevents another turn"),
        ("src", "tests"), ("No second runtime",), ("Stop at denied permission or unknown effect",),
        "source-owned-notes", "existing-budget-and-authority")


def brief(**changes):
    return replace(ChildBrief(mission(), "child-1", "Coordinate recovery proof", ("backend",),
                              ("Return actual restart evidence",)), **changes)


def catalog(**changes):
    out = {"parentThreadId": "parent-1", "inheritedProviderInstanceId": "capacity_fabric",
           "features": {"appOwnedSubagents": True}, "providers": [{"providerInstanceId": "capacity_fabric",
           "canRunChildTask": True, "constraints": [], "models": [{"id": "glm-5.3", "options": [
               {"id": "effort", "values": ["low", "high"]}, {"id": "thinking", "values": [True, False]}]}]}]}
    out.update(changes)
    return out


def child_result(**changes):
    out = {"taskId": "task-1", "childThreadId": "thread-1", "childRunId": "run-1",
           "providerInstanceId": "capacity_fabric", "model": "glm-5.3", "status": "running",
           "workState": "working", "hasPendingChildRuns": False, "hasPendingQuestion": False,
           "pendingApproval": None, "latestTerminalRunId": None, "latestTerminalStatus": None,
           "resultContextTransferId": None, "summary": None}
    out.update(changes)
    return out


def setup():
    native = Native()
    native.responses["orchestrator_capabilities"] = {"structuredContent": catalog()}
    native.responses["delegate_task"] = {"structuredContent": child_result()}
    schemas = {**SCHEMAS, "delegate_task": schema("task", "target", "title", "role", "isolation", "mode", "clientRequestId"),
               "task_status": schema("taskId"), "task_cancel": schema("taskId", "reason", "clientRequestId")}
    client = T3NativeClient(SCOPE, native, schemas)
    return native, NativeParent(client, PARENT)


def delegate(parent, child=None, **kwargs):
    return asyncio.run(parent.delegate(child or brief(), request_id="request-1", model="glm-5.3", **kwargs))


def test_child_has_complete_parent_acceptance_and_isolated_writes():
    child = brief(allowed_write_paths=("src/recovery.py",), role="implementation")
    native, parent = setup(); receipt = delegate(parent, child, options={"effort": "high"})
    args = native.calls[-1][1]
    assert args["isolation"] == "worktree" and args["mode"] == "async"
    assert args["target"] == {"providerInstanceId": "capacity_fabric", "model": "glm-5.3",
                               "options": [{"id": "effort", "value": "high"}]}
    for requirement in child.mission.done_when:
        assert requirement in args["task"]
    assert receipt.parent == PARENT and receipt.child.run_id == "run-1"
    assert receipt.initial_native_status == "running"
    assert receipt.child.delivery == "launched"
    assert "runtimeMode" not in args and "environmentId" not in args


@pytest.mark.parametrize("paths", [("src-other/escape",), ("src/../outside",), ("/src/file",),
                                   ("src/.git/config",), ("src/*.py",), ("src/space name",)])
def test_write_scope_cannot_expand_or_hide_paths(paths):
    with pytest.raises(ValueError):
        brief(allowed_write_paths=paths)


def test_read_only_scope_stays_an_instruction_not_a_permission_claim():
    child = brief()
    assert child.isolation == "shared"
    assert child.document()["scope_is_permission_enforcement"] is False
    assert "native permission mode may be broader" in child.render()


def test_parallel_conflicts_include_ancestor_paths_not_prefixes():
    a = brief(allowed_write_paths=("src/chat",))
    b = brief(child_key="child-2", allowed_write_paths=("src/chat/state.py",))
    c = brief(child_key="child-3", allowed_write_paths=("src/chatting.py",))
    assert len(check_parallel_write_scopes((a, b, c))["write_collisions"]) == 1
    assert check_parallel_write_scopes((a, c))["execution_authority"] is False
    with pytest.raises(ValueError):check_parallel_write_scopes((a, a))


@pytest.mark.parametrize("parent_id", [None, "other-parent", ""])
def test_outside_agent_or_foreign_parent_never_delegates(parent_id):
    native, parent = setup()
    native.responses["orchestrator_capabilities"] = {"structuredContent": catalog(parentThreadId=parent_id)}
    with pytest.raises(Rejected, match="native_parent_not_bound"):delegate(parent)
    assert [x[0] for x in native.calls] == ["orchestrator_capabilities"]


@pytest.mark.parametrize("options", [{"effort": "max"}, {"effort": "xhigh"}, {"thinking": 1},
                                    {"unknown": "high"}, {"effort": None}, False])
def test_reasoning_never_fabricates_supported_modes(options):
    native, parent = setup()
    with pytest.raises((Rejected, ValueError)):delegate(parent, options=options)
    assert not any(name == "delegate_task" for name, _ in native.calls)


def test_options_empty_and_omitted_are_distinct():
    native, parent = setup();delegate(parent)
    assert "options" not in native.calls[-1][1]["target"]
    delegate(parent, options={})
    assert native.calls[-1][1]["target"]["options"] == []


def test_duplicate_model_options_and_catalog_rows_refuse():
    value = catalog(); value["providers"][0]["models"][0]["options"] *= 2
    with pytest.raises(Unavailable):model_options(value, "capacity_fabric", "glm-5.3", {})
    value = catalog(); value["providers"] *= 2
    with pytest.raises(Rejected):model_options(value, "capacity_fabric", "glm-5.3", {})


@pytest.mark.parametrize("changes", [{"childThreadId": "parent-1"}, {"childRunId": None},
                                    {"providerInstanceId": "another-provider"}, {"model": "other"},
                                    {"remoteChild": {"environmentId": "remote", "threadId": "x"}}])
def test_malformed_or_wrong_native_child_effect_is_unknown_not_retry(changes):
    native, parent = setup(); native.responses["delegate_task"] = {"structuredContent": child_result(**changes)}
    with pytest.raises(EffectUnknown):delegate(parent)
    assert sum(name == "delegate_task" for name, _ in native.calls) == 1


def test_lost_dispatch_never_falls_back_or_redelegates():
    native, parent = setup();native.responses["delegate_task"] = TimeoutError("transport lost")
    with pytest.raises(EffectUnknown):delegate(parent)
    assert [x[0] for x in native.calls] == ["orchestrator_capabilities", "delegate_task"]


def test_result_consumption_keeps_original_run_and_parent_acceptance_separate():
    native, parent = setup();receipt = delegate(parent)
    native.responses["task_status"] = {"structuredContent": child_result(status="completed", workState="result_available",
        latestTerminalRunId="run-1", latestTerminalStatus="completed", summary="Original task result")}
    result = asyncio.run(parent.consume_return(receipt, completion_run_id="run-1"))
    assert result["result_ready_for_parent_review"] is True and result["accepted"] is False
    before = len(native.calls)
    with pytest.raises(Conflict):asyncio.run(parent.consume_return(receipt, completion_run_id="run-2"))
    assert len(native.calls) == before


@pytest.mark.parametrize("changes", [{"hasPendingChildRuns": True}, {"hasPendingQuestion": True},
    {"pendingApproval": {"requestId": "approval"}}, {"workState": "waiting_for_children"},
    {"latestTerminalRunId": "newer-run"}, {"status": "failed"}, {"summary": ""}])
def test_turn_complete_or_question_is_not_settled_task(changes):
    native, parent = setup();receipt = delegate(parent)
    value = child_result(status="completed", workState="result_available", latestTerminalRunId="run-1",
                          latestTerminalStatus="completed", summary="result");value.update(changes)
    native.responses["task_status"] = {"structuredContent": value}
    assert asyncio.run(parent.consume_return(receipt, completion_run_id="run-1"))["result_ready_for_parent_review"] is False


def test_lost_status_is_delivery_unknown_not_safe_read_retry():
    native, parent = setup();receipt = delegate(parent)
    native.responses["task_status"] = TimeoutError()
    with pytest.raises(EffectUnknown):asyncio.run(parent.consume_return(receipt, completion_run_id="run-1"))
    assert sum(name == "task_status" for name, _ in native.calls) == 1


def test_same_child_communication_preserves_mission_and_distinct_queued_run():
    native, parent = setup();receipt = delegate(parent)
    message = Communication("question", "Explain the failure without replacing the assignment.",
                            receipt.mission_sha256, mission().source_ref)
    sent = asyncio.run(parent.communicate(receipt, message, request_id="message-2"))
    assert sent.thread == receipt.child.thread and sent.run_id == "run-2"
    assert receipt.child.run_id == "run-1"
    assert receipt.mission_sha256 in native.calls[-1][1]["message"]
    with pytest.raises(Conflict):
        asyncio.run(parent.communicate(receipt, replace(message, mission_sha256="f" * 64), request_id="no-send"))


def test_restart_is_not_implicit_and_cancellation_does_not_require_working_model():
    native, parent = setup();receipt = delegate(parent)
    message = Communication("direction", "stop", receipt.mission_sha256, mission().source_ref)
    with pytest.raises(ValueError):asyncio.run(parent.communicate(receipt, message, request_id="x", mode="restart"))
    native.responses["orchestrator_capabilities"] = TimeoutError()
    native.responses["task_cancel"] = {"structuredContent": {"taskId": "task-1", "status": "cancel_requested"}}
    result = asyncio.run(parent.cancel(receipt, request_id="cancel-1", reason="Explicit user stop"))
    assert result["terminal_observed"] is False and result["accepted"] is False
    assert native.calls[-1][0] == "task_cancel"


@pytest.mark.parametrize("value", ["high", True])
def test_reasoning_configuration_preserves_model_modes_and_other_options(value):
    from integrations.session_bridge.t3_orchestration import set_reasoning
    native, parent = setup();client = parent.client;thread = Thread(SCOPE, "thread-1")
    client.schemas["t3_thread_configure"] = schema("threadId", "modelSelection")
    state = {"threadId": "thread-1", "modelSelection": {"instanceId": "capacity_fabric", "model": "glm-5.3",
             "options": [{"id": "thinking", "value": False}]}, "runtimeMode": "default", "interactionMode": "default"}
    def configure(args):
        if "modelSelection" in args:
            state["modelSelection"] = copy.deepcopy(args["modelSelection"])
            return {"structuredContent": {"sequence": 12}}
        return {"structuredContent": copy.deepcopy(state)}
    native.responses["t3_thread_configure"] = configure
    result = asyncio.run(set_reasoning(client, thread, request_id="reasoning-1",
        option_id="effort" if type(value) is str else "thinking", value=value,
        expected_updated_at=native.detail["thread"]["updatedAt"]))
    assert result["model_changed"] is False and result["native_atomic_precondition"] is False
    assert state["modelSelection"]["model"] == "glm-5.3"
    assert state["runtimeMode"] == "default" and state["interactionMode"] == "default"
    assert result["reasoning_quality_or_provider_obedience"] == "UNPROVEN"
    if type(value) is str:
        assert {"id": "thinking", "value": False} in state["modelSelection"]["options"]


def test_reasoning_noop_does_not_write_and_unsupported_value_is_not_guessed():
    from integrations.session_bridge.t3_orchestration import set_reasoning
    native, parent = setup();client = parent.client;thread = Thread(SCOPE, "thread-1")
    client.schemas["t3_thread_configure"] = schema("threadId", "modelSelection")
    native.responses["t3_thread_configure"] = {"structuredContent": {
        "threadId": "thread-1", "modelSelection": {"instanceId": "capacity_fabric", "model": "glm-5.3",
        "options": [{"id": "effort", "value": "high"}]}, "runtimeMode": "default", "interactionMode": "default"}}
    kw = dict(request_id="reasoning-1", option_id="effort", expected_updated_at=native.detail["thread"]["updatedAt"])
    assert asyncio.run(set_reasoning(client, thread, value="high", **kw))["configuration_written"] is False
    with pytest.raises(Rejected):asyncio.run(set_reasoning(client, thread, value="max", **kw))
    assert not any(name == "t3_thread_configure" and "modelSelection" in args for name, args in native.calls)


def test_reasoning_active_work_is_not_reconfigured():
    from integrations.session_bridge.t3_orchestration import set_reasoning
    native, parent = setup();native.detail["thread"].update(status="running", activeRunId="run-1")
    with pytest.raises(Conflict):
        asyncio.run(set_reasoning(parent.client, Thread(SCOPE, "thread-1"), request_id="x",
            option_id="effort", value="high", expected_updated_at=native.detail["thread"]["updatedAt"]))
    assert not any(name == "t3_thread_configure" for name, _ in native.calls)


def test_reasoning_failed_post_commit_readback_preserves_native_sequence():
    from integrations.session_bridge.t3_orchestration import set_reasoning
    native, parent = setup();client = parent.client;client.schemas["t3_thread_configure"] = schema("threadId", "modelSelection")
    written = []
    def configure(args):
        if "modelSelection" in args:
            written.append(args);return {"structuredContent": {"sequence": 42}}
        if written:return TimeoutError()
        return {"structuredContent": {"threadId": "thread-1", "runtimeMode": "default", "interactionMode": "default",
            "modelSelection": {"instanceId": "capacity_fabric", "model": "glm-5.3", "options": []}}}
    native.responses["t3_thread_configure"] = configure
    with pytest.raises(EffectUnknown) as error:
        asyncio.run(set_reasoning(client, Thread(SCOPE, "thread-1"), request_id="x", option_id="effort",
            value="high", expected_updated_at=native.detail["thread"]["updatedAt"]))
    assert len(written) == 1 and error.value.receipt == {"sequence": 42}
