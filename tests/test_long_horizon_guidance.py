"""Behavior-first tests shared by T3/Claude/Codex and the Hermes consumer."""
import copy
import hashlib
import io
import json
import subprocess
import sys

import pytest

from integrations.session_bridge import project_task_context as source
from integrations.session_bridge import long_horizon_guidance as guide
from integrations.session_bridge import hermes_project_plugin as plugin


def plan():
    return {"schema": source.SCHEMA, "workstream": "WS:FIXTURE", "objective": "Ship the whole outcome",
            "requirements": [{"id": "R1", "text": "Retain recovery"}, {"id": "R2", "text": "Retain mobile"}],
            "allowed_paths": ["app"], "non_goals": ["No second runtime"],
            "tasks": [{"id": key, "title": key, "requirement_ids": [req], "depends_on": deps,
                       "acceptance": [{"id": "A1", "text": "Observe original consumer"}],
                       "state": "pending", "evidence": []}
                      for key, req, deps in (("T1", "R1", []), ("T2", "R1", ["T1"]), ("T3", "R2", []))]}


def raw(value):
    return ("# Plan\n```mastermind-plan\n" + json.dumps(value) + "\n```\n").encode()


def done(value, task_id):
    task = next(t for t in value["tasks"] if t["id"] == task_id)
    task["state"] = "done"
    task["evidence"] = [{"criterion_id": "A1", "result": "pass",
                         "definition_sha256": source.definition_digests(value)[task_id],
                         "ref": "https://github.com/example/repo/commit/" + "a" * 40}]


def view(value):
    return source.project_plan(value, source_sha256=hashlib.sha256(raw(value)).hexdigest(),
                               source_path="docs/plans/fixture.md", workstream="WS:FIXTURE")


def observation(**changes):
    return {"schema": "mastermind.horizon_observation.v1", "workstream": "WS:FIXTURE",
            "task_id": "T1", "native_state": "idle", "effect_state": "settled",
            "user_control": "continue", "remaining_turns": 3,
            "changed_task_ids": [], "recent_attempts": [], **changes}


def advice(value=None, **changes):
    value = value or plan()
    return guide.advise(value, observation(**changes), source_sha256="b" * 64,
                        source_path="docs/plans/fixture.md")


@pytest.mark.parametrize("control, expected", [("stop", "RESPECT_USER_STOP"), ("pause", "KEEP_PAUSED")])
def test_user_control_dominates_every_other_signal(control, expected):
    result = advice(user_control=control, native_state="running", effect_state="unknown", remaining_turns=0)
    assert result["next_action_kind"] == expected
    assert result["advisory_order"] == []
    assert result["native_action"] == "NONE"


@pytest.mark.parametrize("change, expected", [
    ({"effect_state": "unknown"}, "READ_ORIGINAL_EFFECT"),
    ({"effect_state": "denied"}, "PRESERVE_DENIAL_NO_REPLAY"),
    ({"native_state": "running"}, "READ_ACTIVE_RUN"),
    ({"native_state": "awaiting_input"}, "RESOLVE_NATIVE_INPUT"),
    ({"native_state": "unknown"}, "REVALIDATE_NATIVE_CAPABILITY"),
    ({"native_state": "unavailable"}, "REVALIDATE_NATIVE_CAPABILITY"),
    ({"native_state": "stopped"}, "RECONCILE_NATIVE_STOP"),
    ({"remaining_turns": None}, "READ_EXISTING_BUDGET"),
    ({"remaining_turns": 0}, "PRESERVE_BUDGET_BOUNDARY"),
])
def test_native_boundaries_are_not_converted_to_continue(change, expected):
    result = advice(**change)
    assert result["next_action_kind"] == expected
    assert result["execution_authority"] is False
    assert result["observation_authentication"] == "NOT_PERFORMED"


def test_uncertain_effect_holds_only_its_dependency_lane():
    result = advice(effect_state="unknown")
    assert result["held_task_ids"] == ["T1", "T2"]
    assert result["source_ready_ids"] == ["T3"]
    assert result["advisory_order"] == ["T3"]
    assert result["native_action"] == "NONE"


def test_two_same_no_progress_attempts_change_tactic_not_retry():
    rows = [{"task_id": "T1", "hypothesis_sha256": "c" * 64, "made_progress": False}] * 2
    assert advice(recent_attempts=rows)["next_action_kind"] == "CHANGE_HYPOTHESIS_OR_TACTIC"
    changed = [dict(row) for row in rows]
    changed[-1]["hypothesis_sha256"] = "d" * 64
    assert advice(recent_attempts=changed)["next_action_kind"] != "CHANGE_HYPOTHESIS_OR_TACTIC"
    assert advice(recent_attempts=rows, effect_state="unknown")["next_action_kind"] == "READ_ORIGINAL_EFFECT"


def test_successful_delta_breaks_no_progress_sequence():
    rows = [{"task_id": "T1", "hypothesis_sha256": "c" * 64, "made_progress": False},
            {"task_id": "T1", "hypothesis_sha256": "c" * 64, "made_progress": True}]
    assert advice(recent_attempts=rows)["next_action_kind"] == "REVIEW_SOURCE_FOCUS"


def test_native_observations_cannot_target_another_workstream():
    with pytest.raises(source.PlanContextError, match="BINDING"):
        advice(workstream="WS:OTHER")


@pytest.mark.parametrize("change", [
    {"remaining_turns": True}, {"remaining_turns": -1}, {"native_state": []},
    {"effect_state": "success"}, {"changed_task_ids": ["T1", "T1"]},
    {"changed_task_ids": ["UNKNOWN"]}, {"task_id": []},
    {"task_id": None, "effect_state": "unknown"}, {"recent_attempts": [None]},
    {"recent_attempts": [{"task_id": "T1", "hypothesis_sha256": "no", "made_progress": False}]},
    {"recent_attempts": [{"task_id": "T1", "hypothesis_sha256": "c" * 64, "made_progress": 1}]},
])
def test_malformed_observations_are_typed_failures(change):
    with pytest.raises(source.PlanContextError):
        advice(**change)


def test_changed_implementation_reopens_only_affected_descendants():
    value = plan()
    for task in value["tasks"]:
        done(value, task["id"])
    before = copy.deepcopy(value)
    result = advice(value, changed_task_ids=["T1"])
    assert result["reverify_task_ids"] == ["T1", "T2"]
    assert result["source_ready_ids"] == ["T1"]
    assert result["next_action_kind"] == "REVERIFY_AFFECTED_EVIDENCE"
    assert value == before


def test_completion_is_never_product_acceptance():
    value = plan()
    for task in value["tasks"]:
        done(value, task["id"])
    result = advice(value)
    assert result["next_action_kind"] == "REVIEW_PARENT_ACCEPTANCE"
    assert result["mission_accepted"] == "UNOBSERVED"


def test_ranking_unblocks_dependencies_but_never_displaces_active_focus():
    value = plan()
    value["tasks"] = list(reversed(value["tasks"]))
    assert advice(value)["advisory_order"] == ["T1", "T3"]
    value["tasks"][0]["state"] = "in_progress"
    assert advice(value)["focus_task_id"] == "T3"


@pytest.mark.parametrize("kind", ["side_question", "pause", "stop"])
def test_side_question_and_control_cannot_rewrite_mission(kind):
    before, after = plan(), plan()
    after["requirements"][0]["text"] = "Dropped recovery"
    with pytest.raises(source.PlanContextError, match="PRESERVE_SCOPE"):
        guide.check_direction(before, after, kind=kind)
    assert guide.check_direction(before, before, kind=kind)["execution_authority"] is False


def test_refinement_retains_scope_and_invalidates_affected_evidence():
    before, after = plan(), plan()
    after["tasks"][0]["acceptance"][0]["text"] += " after reconnect"
    result = guide.check_direction(before, after, kind="refinement")
    assert result["affected_evidence_task_ids"] == ["T1", "T2"]
    assert result["unchanged_task_ids"] == ["T3"]


def test_replacement_is_distinct_from_refinement_and_is_not_authenticated():
    before, after = plan(), plan()
    after["requirements"] = after["requirements"][:1]
    after["tasks"] = after["tasks"][:2]
    with pytest.raises(source.PlanContextError, match="DROPPED"):
        guide.check_direction(before, after, kind="refinement")
    result = guide.check_direction(before, after, kind="replace_scope")
    assert result["removed_requirement_ids"] == ["R2"]
    assert result["user_intent_authentication"] == "NOT_PERFORMED"


def test_adding_requirement_cannot_rewrite_old_requirement():
    before, after = plan(), plan()
    after["requirements"][0]["text"] = "Different meaning"
    with pytest.raises(source.PlanContextError, match="REWROTE"):
        guide.check_direction(before, after, kind="add_requirement")


def test_compact_context_preserves_blockers_actions_and_native_refs():
    value = plan()
    value["tasks"][1].update(state="blocked", blocker="Original run uncertain", next_action="Read original run")
    value["tasks"][2].update(state="in_progress", execution_lane="delegated", native_ref="runtime:run/original")
    result = guide.compact_context(view(value))
    assert result["task_tree"][1]["blocker"] == "Original run uncertain"
    assert result["task_tree"][1]["next_action"] == "Read original run"
    assert result["task_tree"][2]["native_ref"] == "runtime:run/original"
    assert result["requirements"] == value["requirements"]
    result["requirements"][0]["text"] = "mutation"
    assert value["requirements"][0]["text"] == "Retain recovery"


class Lease:
    disposed = False
    @property
    def active(self):
        return not self.disposed
    def dispose(self):
        self.disposed = True


class NativeContext:
    def __init__(self, bindings):
        self.bindings, self.sections, self.hooks = bindings, {}, {}
        self.lease = Lease()
    def get_config(self, key, default=None):
        assert key == "session_bindings"
        return self.bindings
    def register_system_prompt_section(self, key, callback, **kwargs):
        assert kwargs == {"position": "after_memory", "max_chars": 4000}
        self.sections[key] = callback
        return self.lease
    def register_hook(self, key, callback):
        assert key == "pre_llm_call"
        self.hooks[key] = callback
        return Lease()
    def register_skill(self, name, path, **kwargs):
        assert name == "execute-project" and path.is_file()
        self.skill_lease = Lease()
        return self.skill_lease
    def register_tool(self, **kwargs):
        assert kwargs["override"] is False
        self.tool = kwargs["handler"]
        self.tool_lease = Lease()
        return self.tool_lease


@pytest.fixture
def bound(tmp_path):
    value = plan()
    path = tmp_path / "docs/plans/fixture.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw(value))
    binding = {"workspace_root": str(tmp_path), "plan_path": "docs/plans/fixture.md",
               "workstream": "WS:FIXTURE", "plan_contract_sha256": source.contract_digest(value)}
    ctx = NativeContext({"session-original": binding})
    plugin.register(ctx)
    return value, path, ctx


def test_hermes_bound_turn_uses_same_shared_projection(bound):
    value, path, ctx = bound
    output = ctx.hooks["pre_llm_call"](session_id="session-original", user_message="A side question")
    assert "Retain recovery" in output["context"] and "Retain mobile" in output["context"]
    assert '"focus":{"acceptance"' in output["context"]
    assert ctx.hooks["pre_llm_call"](session_id="unrelated") is None
    assert ctx.sections[plugin.SECTION_ID]({"session_id": "unrelated"}) == ""


def test_hermes_restores_current_progress_without_changing_cached_habits(bound):
    value, path, ctx = bound
    stable = ctx.sections[plugin.SECTION_ID]({"session_id": "session-original"})
    done(value, "T1")
    path.write_bytes(raw(value))
    output = ctx.hooks["pre_llm_call"](session_id="session-original")
    assert '"source_complete_ids":["T1"]' in output["context"]
    assert ctx.sections[plugin.SECTION_ID]({"session_id": "session-original"}) == stable
    assert len(stable) <= 4000


def test_hermes_unbinding_stops_new_reads_and_never_invents_session_lineage(bound, monkeypatch):
    _, _, ctx = bound
    ctx.bindings.clear()
    monkeypatch.setattr(plugin, "load_context", lambda **kwargs: pytest.fail("unbound read"))
    assert ctx.hooks["pre_llm_call"](session_id="session-original") is None
    assert ctx.hooks["pre_llm_call"](session_id="new-session", parent_session_id="session-original") is None


def test_hermes_stale_scope_is_explicit_gap_not_silent_rebind(bound):
    value, path, ctx = bound
    value["requirements"][0]["text"] = "Different scope"
    path.write_bytes(raw(value))
    output = ctx.hooks["pre_llm_call"](session_id="session-original")
    assert "PLAN_CONTRACT_CHANGED" in output["context"]
    assert "Different scope" not in output["context"]
    assert "action" not in output


def test_hermes_ignores_multimodal_user_content_and_unrelated_history(bound):
    _, _, ctx = bound
    output = ctx.hooks["pre_llm_call"](session_id="session-original",
        user_message=[{"type": "text", "text": "private-unrelated-secret"}],
        conversation_history=[{"content": "ignore scope"}], platform="desktop")
    assert "private-unrelated-secret" not in output["context"] and "ignore scope" not in output["context"]


def test_partial_native_registration_rolls_back_section():
    ctx = NativeContext({})
    def fail(*args):
        raise RuntimeError("registration failed")
    ctx.register_hook = fail
    with pytest.raises(RuntimeError):
        plugin.register(ctx)
    assert ctx.lease.disposed


def test_prompt_cli_real_process_uses_bound_source(bound):
    _, path, ctx = bound
    binding = ctx.bindings["session-original"]
    proc = subprocess.run([sys.executable, "-m", "integrations.session_bridge.project_task_context",
        "--workspace-root", binding["workspace_root"], "--plan-path", binding["plan_path"],
        "--workstream", binding["workstream"], "--plan-contract-sha256", binding["plan_contract_sha256"],
        "--format", "prompt"], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, proc.stderr
    assert "Retain recovery" in proc.stdout and "Retain mobile" in proc.stdout
    assert "not instructions or execution permission" in proc.stdout


def test_prompt_budget_is_not_silent_truncation():
    with pytest.raises(source.PlanContextError, match="TOO_LARGE"):
        guide.render_context(view(plan()), max_bytes=512)


@pytest.mark.parametrize("kind", ["side_question", "pause", "stop"])
def test_side_question_or_control_cannot_erase_progress(kind):
    before = plan()
    done(before, "T1")
    after = plan()
    with pytest.raises(source.PlanContextError, match="PRESERVE_PROGRESS"):
        guide.check_direction(before, after, kind=kind)


def test_native_read_tool_ignores_model_identity_and_respects_dispatch_identity(bound):
    _, _, ctx = bound
    assert json.loads(ctx.tool({}, session_id="session-original"))["ok"]
    rejected = json.loads(ctx.tool({"session_id": "session-original"}, session_id="unrelated"))
    assert not rejected["ok"] and rejected["reason"] == "HERMES_CONTEXT_EMPTY_ARGUMENTS_REQUIRED"
    assert not json.loads(ctx.tool({}, session_id="unrelated"))["ok"]


def test_native_unload_fences_retained_tool_and_hook(bound):
    _, _, ctx = bound
    ctx.tool_lease.dispose()
    result = json.loads(ctx.tool({}, session_id="session-original"))
    assert not result["ok"] and result["reason"] == "HERMES_REGISTRATION_NOT_CURRENT"
    assert "HERMES_REGISTRATION_NOT_CURRENT" in ctx.hooks["pre_llm_call"](session_id="session-original")["context"]
    assert ctx.sections[plugin.SECTION_ID]({"session_id": "session-original"}) == ""


def test_configuration_revocation_during_source_read_withholds_context(bound, monkeypatch):
    _, _, ctx = bound
    original = plugin.load_context
    def revoked(**kwargs):
        result = original(**kwargs)
        ctx.bindings.clear()
        return result
    monkeypatch.setattr(plugin, "load_context", revoked)
    result = json.loads(ctx.tool({}, session_id="session-original"))
    assert not result["ok"] and result["reason"] == "HERMES_BINDING_CHANGED_DURING_READ"
    assert "Retain recovery" not in json.dumps(result)


def test_native_compression_predecessor_can_supply_original_binding(bound):
    _, _, ctx = bound
    binding, source_id = plugin._binding(ctx, "native-child", lambda sid: ["session-original", sid])
    assert source_id == "session-original"
    assert binding == ctx.bindings["session-original"]
    assert "native-child" not in ctx.bindings  # no alias registry or copied configuration


def test_native_future_child_cannot_supply_ancestor_binding(bound):
    _, _, ctx = bound
    assert plugin._binding(ctx, "native-ancestor", lambda sid: [sid, "session-original"]) is None


@pytest.mark.parametrize("lineage", [["session-original", "session-original"], [None], "session-original", ["invalid id"]])
def test_malformed_lineage_fails_closed(bound, lineage):
    _, _, ctx = bound
    with pytest.raises(source.PlanContextError, match="LINEAGE_INVALID"):
        plugin._binding(ctx, "native-child", lambda sid: lineage)


def test_conflicting_native_ancestor_bindings_are_not_silently_selected(bound):
    _, _, ctx = bound
    ctx.bindings["middle"] = {**ctx.bindings["session-original"], "workstream": "WS:OTHER"}
    with pytest.raises(source.PlanContextError, match="BINDING_AMBIGUOUS"):
        plugin._binding(ctx, "native-child", lambda sid: ["session-original", "middle", sid])


def test_missing_native_source_does_not_expose_os_error_or_turn_into_success(bound):
    _, path, ctx = bound
    path.unlink()
    result = json.loads(ctx.tool({}, session_id="session-original"))
    assert not result["ok"]
    assert result["reason"] == "PLAN_READ_UNAVAILABLE"
    assert str(path) not in json.dumps(result)


def test_real_prompt_cli_oversized_context_returns_typed_error_without_traceback(bound):
    value, path, ctx = bound
    # A valid 21-KiB project projection fits the JSON reader but not the 20-KiB
    # native prompt delivery budget. No requirement may be silently sliced away.
    value["objective"] = "o" * 8000
    value["non_goals"] = ["x" * 4000, "y" * 4000, "z" * 4000]
    path.write_bytes(raw(value))
    proc = subprocess.run([sys.executable, "-m", "integrations.session_bridge.project_task_context",
        "--workspace-root", str(path.parents[2]), "--plan-path", "docs/plans/fixture.md",
        "--workstream", "WS:FIXTURE", "--plan-contract-sha256", source.contract_digest(value),
        "--format", "prompt"], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 2
    assert "TOO_LARGE" in proc.stderr
    assert "Traceback" not in proc.stderr and proc.stdout == ""


def test_large_off_focus_acceptance_uses_frontier_without_losing_tasks_or_scope(tmp_path):
    value = plan()
    for i in range(4, 19):
        value["tasks"].append({"id": f"T{i}", "title": f"Task {i}", "requirement_ids": ["R2"],
            "depends_on": ["T1"], "acceptance": [{"id": "A1", "text": "d" * 3000}],
            "state": "pending", "evidence": []})
    p = tmp_path / "docs/plans/large.md"
    p.parent.mkdir(parents=True)
    p.write_bytes(raw(value))
    common = {"workspace_root": tmp_path, "relative_path": "docs/plans/large.md",
              "expected_contract_sha256": source.contract_digest(value), "workstream": "WS:FIXTURE"}
    with pytest.raises(source.PlanContextError, match="TOO_LARGE"):
        source.load_context(**common)
    result = source.load_context(**common, context_detail="frontier")
    assert result["requirements"] == value["requirements"]
    assert [t["id"] for t in result["task_tree"]] == [t["id"] for t in value["tasks"]]
    assert result["focus"]["acceptance"] == value["tasks"][0]["acceptance"]
    assert result["source_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert len(guide.render_context(result).encode()) < guide.MAX_PROMPT_BYTES
    assert result["task_detail_scope"] == "FULL_FOCUS; OFF_FOCUS_ACCEPTANCE_AT_EXACT_SOURCE"


def test_packager_keeps_canonical_bytes_and_cannot_overwrite(tmp_path):
    from scripts.build_hermes_long_horizon_plugin import build, MAPPING
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "candidate"
    receipt = build(out)
    assert receipt["installed"] is False
    assert set(receipt["files"]) == set(MAPPING)
    for target, original in MAPPING.items():
        assert (out / target).read_bytes() == (root / original).read_bytes()
        assert receipt["files"][target]["sha256"] == hashlib.sha256((out / target).read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="NEW_ABSOLUTE"):
        build(out)
    with pytest.raises(ValueError, match="NOT_A_NATIVE_INSTALLER"):
        build(tmp_path / ".hermes" / "candidate")


def test_packager_refuses_missing_sources(tmp_path):
    from scripts.build_hermes_long_horizon_plugin import build
    with pytest.raises(ValueError, match="SOURCE_INVALID"):
        build(tmp_path / "candidate", source_root=tmp_path)
    assert not (tmp_path / "candidate").exists()
