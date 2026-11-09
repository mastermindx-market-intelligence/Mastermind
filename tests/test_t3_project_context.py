"""Shared project context through the incumbent T3 client; no live dispatch."""
import asyncio
import copy
import json

import pytest

from integrations.session_bridge import t3_project_context as composition
from integrations.session_bridge import project_task_context as source
from integrations.session_bridge.t3_web_client import CliResult, NativeEffectUnknown, T3CliClient
from tests.test_long_horizon_guidance import plan, view, done

REF = "https://github.com/example/repo/blob/" + "a" * 40 + "/docs/plans/fixture.md"


def brief(context=None, **overrides):
    args = {"request_id": "horizon-fixture", "project_id": "project-fixture", "source_ref": REF}
    args.update(overrides)
    return composition.handoff(context or view(plan()), **args)


def test_existing_brief_preserves_whole_mission_without_granting_write_scope():
    value = brief()
    assert value.allowed_write_paths == () and value.worktree_base is None
    assert "Retain recovery" in value.objective and "Retain mobile" in value.objective
    assert '"execution_authority":false' in value.objective
    assert '"source_path":"docs/plans/fixture.md"' in value.objective
    assert value.source_ref == REF
    assert value.document()["schema"] == "mastermind.t3_handoff_brief.v1"


def test_permitted_write_scope_must_be_explicit_narrow_and_native_isolated():
    value = brief(allowed_write_paths=("app/widgets",), worktree_base="b" * 40)
    assert value.allowed_write_paths == ("app/widgets",)
    with pytest.raises(ValueError, match="worktree"):
        brief(allowed_write_paths=("app",))
    with pytest.raises(source.PlanContextError, match="SCOPE_EXPANDED"):
        brief(allowed_write_paths=("other",), worktree_base="b" * 40)
    with pytest.raises(ValueError):
        brief(allowed_write_paths=("app/../outside",), worktree_base="b" * 40)


@pytest.mark.parametrize("ref", [REF.replace("fixture.md", "other.md"), None, "https://github.com/example/repo/blob/" + "a" * 40])
def test_source_pointer_must_match_the_existing_plan_path(ref):
    with pytest.raises(source.PlanContextError, match="SOURCE_PATH_MISMATCH"):
        brief(source_ref=ref)


def test_mutable_source_ref_does_not_bypass_incumbent_handoff_validator():
    with pytest.raises(ValueError, match="committed"):
        brief(source_ref=REF.replace("a" * 40, "master"))


def test_native_brief_size_limit_is_not_hidden_by_truncation():
    value = plan()
    value["objective"] = "x" * 8000
    with pytest.raises(ValueError):
        brief(view(value))


@pytest.mark.parametrize("kind", ["pause", "stop"])
def test_native_controls_cannot_be_misrepresented_as_queue_next(kind):
    with pytest.raises(source.PlanContextError, match="NATIVE_CONTROL_REQUIRED"):
        composition.followup(view(plan()), user_direction="Stop now", direction_kind=kind)


@pytest.mark.parametrize("kind", [None, [], "steer_now", ""])
def test_unknown_or_unhashable_direction_kind_is_typed_failure(kind):
    with pytest.raises(source.PlanContextError, match="KIND_INVALID"):
        composition.followup(view(plan()), user_direction="Question", direction_kind=kind)


@pytest.mark.parametrize("text", [None, "", "x" * 4097, chr(0xD800)])
def test_bad_user_direction_is_typed_failure(text):
    with pytest.raises(source.PlanContextError, match="DIRECTION_INVALID"):
        composition.followup(view(plan()), user_direction=text, direction_kind="side_question")


def test_side_question_keeps_scope_and_does_not_amend_source():
    original = view(plan())
    before = copy.deepcopy(original)
    message = composition.followup(original, user_direction="Why this approach?", direction_kind="side_question")
    assert "Retain recovery" in message and "Retain mobile" in message
    assert '"source_plan_amended": false' in message
    assert original == before


def test_actual_incumbent_client_composition_preserves_original_thread_and_new_run():
    calls = []
    def runner(invocation):
        calls.append(invocation)
        if invocation.argv[2] == "start":
            return CliResult(0, json.dumps({"projectId": "project-fixture", "threadId": "mcp:original", "runId": "run:1"}))
        return CliResult(0, json.dumps({"threadId": "mcp:original", "runId": "run:2", "delivery": "queued"}))
    async def exercise():
        client = T3CliClient("/fixture-only/t3", runner)
        initial = await client.launch(brief())
        value = plan()
        done(value, "T1")
        direction = composition.followup(view(value), user_direction="Keep mobile simple", direction_kind="refinement")
        continued = await client.send(initial, direction)
        assert initial.thread_id == continued.thread_id == "mcp:original"
        assert continued.run_id == "run:2" and continued.delivery == "queued"
        assert initial.brief_sha256 == continued.brief_sha256
    asyncio.run(exercise())
    assert len(calls) == 2
    assert calls[0].argv[-2:] == ("project-fixture", "-")
    assert calls[1].argv == ("/fixture-only/t3", "thread", "send", "--json", "mcp:original", "-")
    assert '"source_complete_ids":["T1"]' in calls[1].stdin
    assert '"id":"T2"' in calls[1].stdin and "Retain mobile" in calls[1].stdin


def test_lost_followup_response_retains_original_effect_without_replay():
    calls = []
    def runner(invocation):
        calls.append(invocation)
        if len(calls) == 1:
            return CliResult(0, json.dumps({"projectId": "project-fixture", "threadId": "mcp:original", "runId": "run:1"}))
        raise TimeoutError("fixture transport lost")
    async def exercise():
        client = T3CliClient("/fixture-only/t3", runner)
        receipt = await client.launch(brief())
        with pytest.raises(NativeEffectUnknown) as caught:
            await client.send(receipt, composition.followup(view(plan()), user_direction="Question", direction_kind="side_question"))
        assert caught.value.thread_id == "mcp:original"
        assert caught.value.request_id == "horizon-fixture"
    asyncio.run(exercise())
    assert len(calls) == 2
